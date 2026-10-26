"""Bot d montage Saispress (Telegram).

L user kaysifet video (a7san ka Fichier bach Telegram ma ycompressihach) m3a caption:
    #دولي            ← l rkn (ikhtiyari)
    العنوان…
L bot kaydir l montage (montage.py) w kayrje3 l video ka Fichier b nefs l qualité.

Jouj d les APIs:
  - Bot API (HTTP, getUpdates): bach nstqbel l messages. Telegram kay7fed l updates 24 sa3a,
    ya3ni ila l bot kan wa9ef bin jouj runs, ma kaydi3 7tta message.
  - MTProto (Telethon): ghir l tanzil w l irsal d l fichiers (limite 2 GB, Bot API ghir 20/50 MB).
"""
import asyncio
import itertools
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from telethon import Button, TelegramClient
from telethon.sessions import StringSession

import montage

logging.basicConfig(format="%(asctime)s %(message)s", datefmt="%H:%M:%S", level=logging.INFO)
logging.getLogger("telethon").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("montage")

TOKEN = os.environ["VIDEO_BOT_TOKEN"]
API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
ALLOWED = {int(x) for x in re.split(r"[,\s]+", os.environ.get("VIDEO_ALLOWED_IDS", "")) if x.strip()}
RUN_MINUTES = float(os.environ.get("RUN_MINUTES", "330"))
WORK = Path(os.environ.get("WORK_DIR", "work"))
KEEP_BYTES = 6 * 1024**3  # l originaux li kankhliw bach n3awdo l montage b titre jdid

API = f"https://api.telegram.org/bot{TOKEN}"

HELP = (
    "🎬 <b>Bot d montage Saispress</b>\n\n"
    "1. Sifet l video <b>ka Fichier</b> (📎 → Fichier) bach ma ttkhssrch l qualité.\n"
    "2. F caption kteb:\n"
    "<code>#دولي\nالعنوان ديال الخبر</code>\n"
    "(l satr d #rkn ikhtiyari)\n\n"
    "Bot kaysowlek: <b>🏷 Ghir logo</b> wla <b>📰 Logo + titre</b>.\n"
    "Ila khtariti titre w ma ktebtich caption, ghansowlek 3la l 3onwan.\n"
    "Mn ba3d kaysowlek 3la <b>source</b>: platform (X, Instagram…) w smiyt l page wla «متداول», "
    "wla «🔥 متداول» direct bla platform "
    "(katban sghira f jnab l video), w 3la l <b>outro</b> f l akhir.\n"
    "Mn ba3d l montage: «✏️ Bddel titre» w «🔁» (ghir logo ⇄ logo + titre) bla ma t3awed tsifet l video.\n"
    "M3a l video katji <b>cover</b> (JPEG) l Reels.\n"
    "/cancel: tlghi kolchi: l montage li khddam, li f l queue, w l 3onwan li kantsenna."
)


@dataclass
class Job:
    id: str
    chat_id: int
    msg_id: int                 # l message d l video l asli
    filename: str
    title: str = ""
    category: str | None = None
    src: Path | None = None     # l original mnin ytnzel
    created: float = field(default_factory=time.time)
    with_title: bool | None = None  # None: mazal ma khtarch (🏷 ghir logo / 📰 logo + titre)
    fill: bool | None = None        # 4:5...: True crop (full), False cadre; None: mazal ma khtarch
    queued: bool = False
    cancelled: bool = False
    source: tuple[str, str] | None = None  # (platform, smiyt l page wla «متداول»)
    source_asked: bool = False
    outro: bool | None = None   # None: mazal ma khtarch


class Cancelled(Exception):
    """/cancel: l job tlgha."""


jobs: dict[str, Job] = {}
waiting_title: dict[int, str] = {}  # chat_id -> job_id li kantsennaw lih l 3onwan
waiting_source: dict[int, str] = {}  # chat_id -> job_id li kantsennaw lih smiyt l page
queue: asyncio.Queue[str] = asyncio.Queue()
busy: str | None = None
busy_task: asyncio.Task | None = None
_ids = itertools.count(1)


# ───────────────────────── Bot API ─────────────────────────

http = httpx.AsyncClient(timeout=httpx.Timeout(70.0, connect=15.0))


async def api(method: str, **params):
    for attempt in range(4):
        try:
            r = await http.post(f"{API}/{method}", json=params)
            data = r.json()
        except (httpx.HTTPError, ValueError) as e:
            log.warning("[api] %s: %s", method, type(e).__name__)
            await asyncio.sleep(2 ** attempt)
            continue
        if data.get("ok"):
            return data["result"]
        retry = data.get("parameters", {}).get("retry_after")
        if retry:
            await asyncio.sleep(retry + 1)
            continue
        if "message is not modified" not in data.get("description", ""):
            log.warning("[api] %s: %s", method, data.get("description"))
        return None
    return None


async def say(chat_id: int, text: str, reply_to: int | None = None, buttons=None) -> int | None:
    params = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if reply_to:
        params["reply_parameters"] = {"message_id": reply_to, "allow_sending_without_reply": True}
    if buttons:
        params["reply_markup"] = {"inline_keyboard": buttons}
    res = await api("sendMessage", **params)
    return res["message_id"] if res else None


async def edit(chat_id: int, msg_id: int | None, text: str) -> None:
    if msg_id:
        await api("editMessageText", chat_id=chat_id, message_id=msg_id, text=text, parse_mode="HTML")


# ───────────────────────── parsing ─────────────────────────

def parse_caption(text: str) -> tuple[str | None, str]:
    """'#دولي\\nالعنوان' -> ('دولي', 'العنوان'). L rkn ikhtiyari."""
    lines = [ln.strip() for ln in (text or "").strip().splitlines() if ln.strip()]
    category = None
    if lines and lines[0].startswith("#"):
        category = lines.pop(0).lstrip("#").replace("_", " ").strip() or None
    return category, " ".join(lines)


def video_of(msg: dict) -> tuple[str, int] | None:
    """(smiya, 7ajm) ila l message fih video (video wla fichier video)."""
    if v := msg.get("video"):
        return v.get("file_name") or "video.mp4", v.get("file_size", 0)
    d = msg.get("document")
    if d and (d.get("mime_type", "").startswith("video/")
              or re.search(r"\.(mp4|mov|m4v|mkv|webm|avi|3gp)$", d.get("file_name", ""), re.I)):
        return d.get("file_name") or "video.mp4", d.get("file_size", 0)
    return None


def esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ───────────────────────── updates ─────────────────────────

CHOICE = "Chno ndir l had l video?"


FILL_CHOICE = "📐 Video machi 9:16 (b7al 4:5). F version frame:"


def fill_buttons(job_id: str) -> list:
    return [[{"text": "✂️ Crop (full)", "callback_data": f"fc:{job_id}"},
             {"text": "🖼 B cadre", "callback_data": f"fb:{job_id}"}]]


def choice_buttons(job_id: str) -> list:
    return [[{"text": "🏷 Ghir logo", "callback_data": f"lg:{job_id}"},
             {"text": "📰 Logo + titre", "callback_data": f"tt:{job_id}"}]]


SRC_CHOICE = "📹 Nzid source f l video?"
TRENDING = "متداول"


def source_buttons(job_id: str) -> list:
    return [[{"text": "✅ Zid source", "callback_data": f"sy:{job_id}"},
             {"text": "❌ Bla source", "callback_data": f"sn:{job_id}"}]]


def platform_buttons(job_id: str) -> list:
    pl = [{"text": n, "callback_data": f"sp:{job_id}:{i}"} for i, n in enumerate(montage.PLATFORMS)]
    return [pl[:3], pl[3:], [{"text": f"🔥 {TRENDING}", "callback_data": f"sp:{job_id}:t"}]]


OUTRO_CHOICE = "🎞 Nzid l outro f l akhir?"


async def proceed(job: Job) -> None:
    """Mor ikhtiyar titre: nsowlo 3la source, mn ba3d l outro (mra wa7da l kol video), mn ba3d l queue."""
    if not job.source_asked:
        job.source_asked = True
        await say(job.chat_id, SRC_CHOICE, reply_to=job.msg_id, buttons=source_buttons(job.id))
    elif job.outro is None:
        await say(job.chat_id, OUTRO_CHOICE, reply_to=job.msg_id,
                  buttons=[[{"text": "✅ Ah", "callback_data": f"oy:{job.id}"},
                            {"text": "❌ La", "callback_data": f"on:{job.id}"}]])
    else:
        await enqueue(job)


async def ask_title(job: Job) -> None:
    waiting_title[job.chat_id] = job.id
    await say(job.chat_id, "✍️ Sifet l 3onwan.\n(Ila bghiti l rkn: <code>#دولي</code> f satr lowel)",
              reply_to=job.msg_id)


async def enqueue(job: Job) -> None:
    job.queued = True
    await queue.put(job.id)
    ahead = queue.qsize() - 1 + (1 if busy else 0)
    if ahead:
        await say(job.chat_id, f"🕒 F l queue: {ahead} 9bel menha.", reply_to=job.msg_id)


def cancel_all(chat_id: int) -> int:
    """Kayms7 l jobs d had chat men l queue w kayw99ef li khddam. Kayrje3 ch7al tlgha."""
    keep, n = [], 0
    while not queue.empty():
        jid = queue.get_nowait()
        queue.task_done()
        job = jobs.get(jid)
        if job and job.chat_id == chat_id:
            job.queued, n = False, n + 1
        else:
            keep.append(jid)
    for jid in keep:
        queue.put_nowait(jid)
    job = jobs.get(busy) if busy else None
    if job and job.chat_id == chat_id and busy_task and not busy_task.done():
        job.cancelled = True  # ffmpeg kaywe99ef f l progress (thread), w l task kattlgha
        busy_task.cancel()
        n += 1
    return n


async def on_message(msg: dict) -> None:
    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()

    if text in ("/start", "/help"):
        await say(chat_id, HELP)
        return
    if text == "/cancel":
        waiting_title.pop(chat_id, None)
        waiting_source.pop(chat_id, None)
        n = cancel_all(chat_id)
        await say(chat_id, f"✔️ Tlgha ({n} video)." if n else "✔️ Tlgha.")
        return

    vid = video_of(msg)
    if vid:
        name, size = vid
        if size > 2000 * 1024**2:
            await say(chat_id, "❌ L video kbira bzaf (l a9sa 2 GB).", reply_to=msg["message_id"])
            return
        job = Job(f"j{next(_ids)}", chat_id, msg["message_id"], name)
        job.category, job.title = parse_caption(msg.get("caption", ""))
        jobs[job.id] = job
        if msg.get("video") and not msg.get("document"):
            await say(chat_id, "ℹ️ Sifetti l video ka «Vidéo»: Telegram ymken compressaha. "
                               "L a7san ka Fichier (📎 → Fichier).", reply_to=msg["message_id"])
        await say(chat_id, CHOICE, reply_to=msg["message_id"], buttons=choice_buttons(job.id))
        return

    if text and chat_id in waiting_source:
        job = jobs.get(waiting_source.pop(chat_id))
        if not job or not job.source:
            return
        name = montage.clean_source(text)
        if not name:
            waiting_source[chat_id] = job.id
            await say(chat_id, "❌ Smiya khawya, 3awed.")
            return
        job.source = (job.source[0], name)
        await say(chat_id, f"📹 Source: <b>{esc(job.source[0])} | {esc(name)}</b>")
        await proceed(job)
        return

    if text and chat_id in waiting_title:
        job = jobs.get(waiting_title.pop(chat_id))
        if not job:
            return
        category, title = parse_caption(text)
        if not montage.clean_title(title):
            waiting_title[chat_id] = job.id
            await say(chat_id, "❌ 3onwan khawi, 3awed.")
            return
        job.title, job.with_title = title, True
        if category:  # titre jdid bla rkn: kankhliw l rkn l 9dim
            job.category = category
        await proceed(job)
        return

    if text:
        await say(chat_id, "Sifet video (ka Fichier) m3a l 3onwan f caption. /help")


async def on_callback(cb: dict) -> None:
    data = cb.get("data", "")
    chat_id = cb["message"]["chat"]["id"]
    if data[:3] in ("lg:", "tt:"):  # ikhtiyar lowel: ghir logo / logo + titre
        job = jobs.get(data[3:])
        if not job or job.with_title is not None:
            await api("answerCallbackQuery", callback_query_id=cb["id"], text="Deja khtariti.")
            return
        job.with_title = data.startswith("tt:")
        await api("answerCallbackQuery", callback_query_id=cb["id"])
        await api("editMessageText", chat_id=chat_id, message_id=cb["message"]["message_id"], parse_mode="HTML",
                  text=f"{CHOICE}\n→ <b>{'📰 Logo + titre' if job.with_title else '🏷 Ghir logo'}</b>")
        if job.with_title and not job.title:
            await ask_title(job)
        else:
            await proceed(job)
        return
    if data[:3] in ("sy:", "sn:", "sp:"):  # source: wach, platform, mn ba3d smiya (message) wla متداول
        parts = data.split(":")
        job = jobs.get(parts[1])
        mid = cb["message"]["message_id"]
        if not job or job.queued:
            await api("answerCallbackQuery", callback_query_id=cb["id"], text="Deja khtariti.")
            return
        await api("answerCallbackQuery", callback_query_id=cb["id"])
        if data.startswith("sn:"):
            job.source = None
            waiting_source.pop(chat_id, None)
            await api("editMessageText", chat_id=chat_id, message_id=mid, parse_mode="HTML",
                      text=f"{SRC_CHOICE}\n→ <b>❌ Bla source</b>")
            await proceed(job)
        elif data.startswith("sy:"):
            await api("editMessageText", chat_id=chat_id, message_id=mid, parse_mode="HTML",
                      text=f"📹 Mnin jat l video? (wla 🔥 {TRENDING})", reply_markup={"inline_keyboard": platform_buttons(job.id)})
        elif parts[2] == "t":  # متداول bla platform: ghir l khatt dahbi f l video
            job.source = ("", TRENDING)
            waiting_source.pop(chat_id, None)
            await api("editMessageText", chat_id=chat_id, message_id=mid, parse_mode="HTML",
                      text=f"📹 Source: <b>🔥 {TRENDING}</b>")
            await proceed(job)
        else:
            job.source = (montage.PLATFORMS[int(parts[2])], "")
            waiting_source[chat_id] = job.id
            await api("editMessageText", chat_id=chat_id, message_id=mid, parse_mode="HTML",
                      text=f"📹 <b>{esc(job.source[0])}</b>\n✍️ Kteb smiyt l page (@...), wla clicki «{TRENDING}».",
                      reply_markup={"inline_keyboard": [[{"text": TRENDING, "callback_data": f"st:{job.id}"}]]})
        return
    if data.startswith("st:"):  # source: متداول
        job = jobs.get(data[3:])
        if not job or job.queued or not job.source or waiting_source.get(chat_id) != job.id:
            await api("answerCallbackQuery", callback_query_id=cb["id"], text="Deja khtariti.")
            return
        waiting_source.pop(chat_id)
        job.source = (job.source[0], TRENDING)
        await api("answerCallbackQuery", callback_query_id=cb["id"])
        await api("editMessageText", chat_id=chat_id, message_id=cb["message"]["message_id"], parse_mode="HTML",
                  text=f"📹 Source: <b>{esc(job.source[0])} | {TRENDING}</b>")
        await proceed(job)
        return
    if data[:3] in ("oy:", "on:"):  # outro: ah / la
        job = jobs.get(data[3:])
        if not job or job.queued or job.outro is not None:
            await api("answerCallbackQuery", callback_query_id=cb["id"], text="Deja khtariti.")
            return
        job.outro = data.startswith("oy:")
        await api("answerCallbackQuery", callback_query_id=cb["id"])
        await api("editMessageText", chat_id=chat_id, message_id=cb["message"]["message_id"], parse_mode="HTML",
                  text=f"{OUTRO_CHOICE}\n→ <b>{'✅ Ah' if job.outro else '❌ La'}</b>")
        await enqueue(job)
        return
    if data[:3] in ("fc:", "fb:"):  # 4:5: crop wla cadre (mor tanzil)
        job = jobs.get(data[3:])
        if not job or job.fill is not None or job.queued:
            await api("answerCallbackQuery", callback_query_id=cb["id"], text="Deja khtariti.")
            return
        if not (job.src and job.src.exists()):
            await api("answerCallbackQuery", callback_query_id=cb["id"],
                      text="L original ma b9ach, 3awed sifet l video.", show_alert=True)
            return
        job.fill = data.startswith("fc:")
        await api("answerCallbackQuery", callback_query_id=cb["id"])
        await api("editMessageText", chat_id=chat_id, message_id=cb["message"]["message_id"], parse_mode="HTML",
                  text=f"{FILL_CHOICE}\n→ <b>{'✂️ Crop (full)' if job.fill else '🖼 B cadre'}</b>")
        await enqueue(job)
        return
    if data.startswith("sw:"):  # mor l montage: ghir logo ⇄ logo + titre
        job = jobs.get(data[3:])
        if not job or not (job.src and job.src.exists()):
            await api("answerCallbackQuery", callback_query_id=cb["id"],
                      text="L original ma b9ach, 3awed sifet l video.", show_alert=True)
            return
        if job.queued:
            await api("answerCallbackQuery", callback_query_id=cb["id"], text="Mazal kaytmonta.")
            return
        job.with_title = not job.with_title
        await api("answerCallbackQuery", callback_query_id=cb["id"])
        if job.with_title and not job.title:
            await ask_title(job)
        else:
            await enqueue(job)
        return
    if data.startswith("rt:"):
        job = jobs.get(data[3:])
        if not job or not (job.src and job.src.exists()):
            await api("answerCallbackQuery", callback_query_id=cb["id"],
                      text="L original ma b9ach, 3awed sifet l video.", show_alert=True)
            return
        if job.queued:
            await api("answerCallbackQuery", callback_query_id=cb["id"], text="Mazal kaytmonta.")
            return
        waiting_title[chat_id] = job.id
        await api("answerCallbackQuery", callback_query_id=cb["id"])
        await say(chat_id, "✍️ Sifet l 3onwan jdid (w #rkn f satr lowel ila bghiti tbddlo).")
        return
    await api("answerCallbackQuery", callback_query_id=cb["id"])


async def poll(deadline: float) -> None:
    offset = None
    while time.time() < deadline:
        params = {"timeout": 50, "allowed_updates": ["message", "callback_query"]}
        if offset:
            params["offset"] = offset
        updates = await api("getUpdates", **params)
        for u in updates or []:
            offset = u["update_id"] + 1
            try:
                src = u.get("message") or u.get("callback_query")
                if not src or src.get("from", {}).get("id") not in ALLOWED:
                    continue  # ghrib: bla jawab
                if "message" in u:
                    if u["message"]["chat"]["type"] == "private":
                        await on_message(u["message"])
                else:
                    await on_callback(u["callback_query"])
            except Exception:
                log.exception("[update] fchel")
    if offset:  # n2ekdo l updates li t9raw bach ma yt3awdouch f run jay
        await api("getUpdates", offset=offset, timeout=0)


# ───────────────────────── khedma ─────────────────────────

def _bar(x: float) -> str:
    n = int(x * 10)
    return "▰" * n + "▱" * (10 - n) + f" {x:.0%}"


def _free_space() -> None:
    """Kanms7o l originaux l 9dam ila fatu KEEP_BYTES."""
    pending = set(queue._queue)  # ma nms7ouch original d job mazal f l queue
    done = sorted((j for j in jobs.values() if j.src and j.src.exists() and j.id not in pending),
                  key=lambda j: j.created)
    total = sum(j.src.stat().st_size for j in done)
    for j in done:
        if total <= KEEP_BYTES:
            break
        total -= j.src.stat().st_size
        shutil.rmtree(j.src.parent, ignore_errors=True)
        j.src = None


async def process(client: TelegramClient, job: Job) -> None:
    status = await say(job.chat_id, "⬇️ Kantnzel l video…", reply_to=job.msg_id)
    last = [0.0]
    done = [False]

    async def tick(text: str, x: float) -> None:
        if done[0]:
            return
        if time.time() - last[0] > 4 or x >= 1:
            last[0] = time.time()
            await edit(job.chat_id, status, f"{text}\n{_bar(x)}")

    t0 = time.time()
    if not (job.src and job.src.exists()):
        msg = await client.get_messages(None, ids=job.msg_id)  # private chat: l ID kafi
        if not msg or not msg.media:
            raise RuntimeError("ma l9itch l video f Telegram")
        folder = WORK / job.id
        folder.mkdir(parents=True, exist_ok=True)
        ext = Path(job.filename).suffix or ".mp4"
        job.src = Path(await client.download_media(
            msg, file=str(folder / f"src{ext}"),
            progress_callback=lambda d, t: asyncio.ensure_future(tick("⬇️ Kantnzel l video…", d / t if t else 0))))
    t_dl = time.time() - t0

    loop = asyncio.get_running_loop()
    src_p = await asyncio.to_thread(montage.probe, job.src)
    if job.fill is None and montage.fill_choice(src_p):  # 4:5: nsowlo 9bel l montage (l original tnzel)
        done[0] = True
        await api("deleteMessage", chat_id=job.chat_id, message_id=status)
        await say(job.chat_id, FILL_CHOICE, reply_to=job.msg_id, buttons=fill_buttons(job.id))
        return
    # 9:16: jouj versions (frame b animation 9bel, mn ba3d zoom + panel); 3rida: frame bo7dha
    versions = [None] if montage.framed(src_p) else [True, False]
    chat = await msg_chat(client, job)
    t_mt, sizes = 0.0, []
    for vi, frame in enumerate(versions):
        tag = f" ({vi + 1}/{len(versions)})" if len(versions) > 1 else ""
        out = job.src.parent / f"saispress_{job.id}_{int(time.time())}_{vi}.mp4"

        def prog(x: float, tag=tag) -> None:
            if job.cancelled:
                raise Cancelled
            asyncio.run_coroutine_threadsafe(tick(f"🎬 Montage{tag}…", x), loop)

        t1 = time.time()
        p = await asyncio.to_thread(montage.montage, job.src, out, job.title, job.category, prog,
                                    bool(job.with_title), frame, job.fill is not False, job.source,
                                    bool(job.outro))
        t_mt += time.time() - t1

        await edit(job.chat_id, status, f"⬆️ Kansifet l video{tag}…")
        thumb = await asyncio.to_thread(montage.thumbnail, out, out.with_suffix(".jpg"), min(1.0, p.duration / 2))
        cover = await asyncio.to_thread(montage.cover_image, out,
                                        out.with_name(f"saispress_cover_{job.id}_{vi}.jpg"),
                                        montage.cover_time(p, bool(job.with_title), frame))
        size_mb = out.stat().st_size / 1024**2
        sizes.append(size_mb)
        W, H, _ = montage.out_size(p, frame)
        style = {False: "📱 Version 9dima (zoom)\n", True: "🖼 Version frame\n"}.get(frame, "")
        caption = (style + (f"{job.title}\n\n" if job.with_title else "🏷 Ghir logo\n\n")
                   + (f"📹 {' | '.join(filter(None, job.source))}\n" if job.source and job.source[1] else "")
                   + f"{W}×{H} · {p.fps:.0f} fps · {size_mb:.1f} MB")
        buttons = ([Button.inline("✏️ Bddel titre", data=f"rt:{job.id}".encode())] if job.with_title else []) + \
            [Button.inline("🔁 Ghir logo" if job.with_title else "🔁 Logo + titre", data=f"sw:{job.id}".encode())]
        sent = await client.send_file(
            chat, str(out), caption=caption[:1000], parse_mode=None, force_document=True, thumb=str(thumb),
            reply_to=job.msg_id, buttons=[buttons],
            progress_callback=lambda d, t, tag=tag: asyncio.ensure_future(
                tick(f"⬆️ Kansifet l video{tag}…", d / t if t else 0)))
        await client.send_file(chat, str(cover), caption="🖼 Cover (Reels → Edit cover → mn l galerie)",
                               force_document=True, reply_to=sent.id)
        out.unlink(missing_ok=True)
        thumb.unlink(missing_ok=True)
        cover.unlink(missing_ok=True)
    done[0] = True
    await api("deleteMessage", chat_id=job.chat_id, message_id=status)
    log.info("[job %s] %s · tanzil %.0fs · montage %.0fs · %s MB", job.id, job.filename, t_dl, t_mt,
             " + ".join(f"{m:.1f}" for m in sizes))


_chats: dict[int, object] = {}


async def msg_chat(client: TelegramClient, job: Job):
    """InputPeer d l user (Telethon khasso access_hash; kanjibouh men l message)."""
    if job.chat_id not in _chats:
        msg = await client.get_messages(None, ids=job.msg_id)
        _chats[job.chat_id] = await msg.get_input_chat()
    return _chats[job.chat_id]


async def worker(client: TelegramClient) -> None:
    global busy, busy_task
    while True:
        job_id = await queue.get()
        busy = job_id
        job = jobs[job_id]
        job.cancelled = False
        busy_task = asyncio.create_task(process(client, job))
        try:
            await busy_task
        except (asyncio.CancelledError, Cancelled):
            if not job.cancelled:  # l worker bo7do tlgha (akhir d run)
                raise
            log.info("[job %s] tlgha", job_id)
        except Exception as e:
            log.exception("[job %s] fchel", job_id)
            await say(job.chat_id, f"❌ Montage fchel: {esc(str(e))[:300]}", reply_to=job.msg_id)
        finally:
            job.queued = False
            busy, busy_task = None, None
            queue.task_done()
            _free_space()


async def main() -> None:
    if not ALLOWED:
        raise SystemExit("VIDEO_ALLOWED_IDS khawi")
    WORK.mkdir(parents=True, exist_ok=True)
    # l 7sab mn bdya d l job (JOB_START), machi mn bdya d l bot: ila t3llat l install, GitHub kay9te3 l job
    # (timeout-minutes) 9bel ma nlanciw run jay
    start = float(os.environ.get("JOB_START") or time.time())
    deadline = start + RUN_MINUTES * 60
    me = await api("getMe")
    hook = await api("getWebhookInfo")
    if hook and hook.get("url"):  # getUpdates ma kaykhdemch m3a webhook
        await api("deleteWebhook")
    await api("setMyCommands", commands=[{"command": "help", "description": "Kifach nkhdem b l bot"},
                                         {"command": "cancel", "description": "Lghi kolchi (montage, queue, 3onwan)"}])
    client = TelegramClient(StringSession(), API_ID, API_HASH, receive_updates=False)
    await client.start(bot_token=TOKEN)
    log.info("[start] @%s · %d user · %.0f d9i9a", me["username"] if me else "?", len(ALLOWED),
             (deadline - time.time()) / 60)
    w = asyncio.create_task(worker(client))
    try:
        await poll(deadline)
        # ma kanstqblouch jdid; kansaliw l queue
        await queue.join()
    finally:
        w.cancel()
        await client.disconnect()
        await http.aclose()
    log.info("[stop] %d job f had run", len(jobs))


if __name__ == "__main__":
    asyncio.run(main())
