# Saispress montage bot

Bot Telegram: katsifet lih video, w kayrj3ha lik **9:16** b logo Saispress w titre f panel navy
b animation, **b nefs l qualité**.

## Kifach katkhdem bih (men telephone)

1. Sifet l video **ka Fichier**: 📎 → Fichier → khtar l video. Ila sifetiha ka «Vidéo», Telegram kaycompressiha.
2. F caption kteb:
   ```
   #دولي
   العنوان ديال الخبر
   ```
   Satr `#rkn` ikhtiyari.
   L bot kaysowlek: **🏷 Ghir logo** wla **📰 Logo + titre**. Ila khtariti titre w ma ktebtich caption, kaysowlek 3la l 3onwan.
   Mn ba3d kaysowlek: **📹 Zid source** wla **Bla source**. Ila zditi: platform (X, Instagram, TikTok, Facebook, YouTube),
   mn ba3d kteb smiyt l page (`@...`) wla clicki «متداول». Mn ba3d: **🎞 Outro** ah wla la.
3. L bot kayban lik l progress (tanzil → montage → irsal), w kayrje3 l video ka Fichier.
4. **✏️ Bddel titre**: kat3awed l montage b 3onwan jdid bla ma t3awed tsifet l video.
   **🔁 Ghir logo / 🔁 Logo + titre**: kat3awed l montage b l format lakhor.
   M3a kol video katji **cover** (JPEG 1080×1920 b nefs l design) l Reels: «Edit cover» → mn l galerie.
   Hadchi kaykhdem ghir f nefs l run, ya3ni ~5 sa3at men ba3d l montage.

**🔗 Link:** sifet ghir link d l video (Instagram, TikTok, X, Facebook, YouTube…). L bot kaytnzelha (yt-dlp, a7san qualité),
w Gemini (free tier, Secret `GEMINI_API_KEY`) kayktb mn l post: **titre** (kaydkhel f l montage) w **description** l Instagram
(message bo7dha, copier direct), w **rkn** men lista d news bot (سياسة، اقتصاد، مجتمع، حوادث، رياضة، دولي، ثقافة، صحة، تعليم، طقس، تكنولوجيا، فن). Mn ba3d: source → outro → montage. Mor l montage: «✏️ Bddel titre» w «🏷 Bddel rkn» (lista d arkan → montage jdid).
Bla key / quota / ma3loumat na9sa: l bot kaygoul w kaysowl 🏷 / 📰 (titre katktbo nta). Models: Variable `GEMINI_MODELS` (ikhtiyari).
Instagram / YouTube / X ymken ytlbo login men serveurs d GitHub: zid Secret `YTDLP_COOKIES` (contenu d `cookies.txt`, format Netscape).

`/help`: l m3awna · `/cancel`: tlghi kolchi (l montage li khddam, li f l queue, w l 3onwan li kaytsenna).

## Chno kaydir l montage

- **Format:** output dima 9:16, f l a9al 1080×1920 (l titre w l logo kaytrsmo 7addin 7tta ila l video sghira).
  Video 9:16 kbira katb9a b résolution dyalha. Video machi 9:16: zoom in 7tta t3mer l cadre kaml (crop f l wst), bla flou.
- **Video 3rida (16:9, 4:3, mrabba3a): frame 9:16** (b7al reels d l akhbar), l video kamla bla crop:
  - L video f l wost, w l fond = nefs l video mdbbla b tint navy.
  - L fo9: logo l imin, `#rkn` l issar.
  - Ta7t l video: flèches dahbiyin + titre kbir b khatt dahbi.
  - `#عاجل`: block 7mer ta7t l video b label «عاجل».
  - Titre kaydkhel b animation (flèches, mn ba3d stoura kaytkchfo men l imin, ~1.2 s) w kayb9a l video kamla
    (Reels kayakhod cover mn l frame).
- **Ghir logo:** nefs l frame (logo + `#rkn`) bla titre. Video 9:16: bla panel.
- **Video 9:16 / 4:5:** version wa7da: 🖼 frame (video full 9:16, logo + `#rkn` l fo9 b dégradé navy, titre l t7t b animation, strock navy r9i9 7wl l ktaba).
  Bouton «📱 Version 9dima» ta7t l video → l version zoom (panel b animation), w «🖼 Version frame» bach trje3; kol wa7da b cover dyalha. Video 4:5 / 3:4 (machi 9:16): l bot kaysowl mor tanzil: ✂️ Crop (full) wla
  🖼 B cadre (video 3amra jnab b 3ard kaml, f l wost, fond mdbbel fo9 w ta7t; logo + `#rkn` mhbtin chwiya, titre fo9 l video).
- **Logo:** l fo9 3la l imin, l video kamla.
- **Source (ikhtiyari):** sghira f jnab l issar (~35% men l fo9, b7al l medias): icon d l platform l fo9 | smiyt l page
  wla «متداول», ktaba byda 3amoudiya (kat9ra men l t7t l l fo9) b shadow, bla fond. Dkhla: khatt dahbi kaykber w kaymsa7
  w l ktaba katban mn ta7to; katb9a kamla `SOURCE_SECONDS` (1 s) w katkhrej b l39s (~2.7 s f l kol).
- **Animation d l logo (~1.4 s, f ga3 l versions):** l 7rf kaytktb men l imin l l issar (7afa mayla rtba b daw dahbi)
  m3a zoom kayrtta7 (1.12 → 1), mn ba3d mrab3at PRESS kaytl3o wa7d b wa7d (pop), w f l akhir lam3a r9i9a 3la l 7rf.
  F frame: l cadre d `#rkn` kaytfta7 men l issar, «#» kaybrez, w l ktaba katkchef.
- **Outro (ikhtiyari, ~3.4 s, f ga3 l versions):** l video kat7bes f akhir frame, bandat mayliin (dahbi, navy, fond) b motion blur
  kaygttiwha men l imin; logo jdid (`assets/logo_wide.png`): l khatt ta7ti kaytktb b 7afa dahbiya + streak, snan kaytl3o,
  n9at, PRESS, lam3a; mn ba3d khatt dahbi, «تابعونا لكل جديد», pill `saispress.com` w icons f dwayr. Fond navy b daw, camera
  push-in w grain (`OUTRO_GRAIN`, 0 = bla). L son kaytfada f akhir l video (bla son f l outro). `OUTRO_SITE` bach tbddel l site.
- **Titre f frame:** 16:9: shadow sghir mora l ktaba. 9:16 / 4:5 (titre fo9 l video): strock navy r9i9 (`TITLE_STROKE`), yban 7tta 3la fond byed.
- **Titre:** panel navy + khatt gold + pill d l rkn.
  - Dkhla ~0.45s: panel f 3 tba9at kaymsa7o men l issar l l imin, l titre kayban m3a tba9a lkhra.
  - Kaybqa `TITLE_SECONDS` (4.2s).
  - Khrja ~0.35s.
- **Qualité:**
  - x264 CRF 17 preset slow (visually lossless), nefs l fps.
  - L son kaytnsakh kif howa.
  - HDR d iPhone kaytbddel l SDR b tone-mapping.
- **Limite:** 2 GB l video (MTProto).

## Setup (mra wa7da)

1. **Bot:** f Telegram, @BotFather → `/newbot` → khod l **token**.
2. **API:** my.telegram.org → login → *API development tools* → khod **api_id** w **api_hash**.
3. **GitHub** → had l repo → Settings → Secrets and variables → Actions:
   - *Secrets*: `VIDEO_BOT_TOKEN`, `TG_API_ID`, `TG_API_HASH`
   - *Variables*:
     - `VIDEO_ALLOWED_IDS` = IDs d l équipe, mfr9in b virgule (ex: `5757985158,123456789`).
     - `VIDEO_BOT_ENABLED` = `true`.
4. **Actions** → *Montage bot* → *Run workflow*. Mn ba3d, l bot kaybqa khddam 24/24 b rasso.

Ma tsifet 7tta wa7ed men had l codes f chat wla f l code. Blasthom ghir GitHub Secrets.

Bach t3ref ID dyal chi wa7ed: ysifet message l @userinfobot.

### Variables ikhtiyariyin
| Variable | Default | Chno kaydir |
|---|---|---|
| `TITLE_SECONDS` | `4.2` | ch7al ybqa l titre kaml |
| `MONTAGE_CRF` | `17` | qualité (a9el = a7san w fichier kber) |
| `MONTAGE_PRESET` | `slow` | `medium` = asra3, chwiya kber f l 7ajm |
| `RUN_MINUTES` | `330` | 3omr kol run |

## Kifach khddam
- `bot.py`:
  - Bot API (`getUpdates`) l l messages: Telegram kay7fed l messages 24 sa3a, ya3ni ma kaydi3 walou bin runs.
  - Telethon (MTProto) l tanzil/irsal d fichiers 7tta l 2 GB.
- `montage.py`:
  - Pillow kayrsem l panel (frame b frame) w l logo.
  - ffmpeg kaydir l composition w l encodage.
  - Tajriba: `python montage.py in.mp4 out.mp4 "العنوان" "دولي"`.
- `.github/workflows/montage-bot.yml`: chaîne 24/24, kol run ~5h30 kaylanci li moraha.

**Tanbih:** had l repo public. Logs d Actions kaybanou l ay wa7ed (fihom l 3anawin w smiyat l fichiers, bla codes).
