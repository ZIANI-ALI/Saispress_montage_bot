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
3. L bot kayban lik l progress (tanzil → montage → irsal), w kayrje3 l video ka Fichier.
4. **✏️ Bddel titre**: kat3awed l montage b 3onwan jdid bla ma t3awed tsifet l video.
   **🔁 Ghir logo / 🔁 Logo + titre**: kat3awed l montage b l format lakhor.
   M3a kol video katji **cover** (JPEG 1080×1920 b nefs l design) l Reels: «Edit cover» → mn l galerie.
   Hadchi kaykhdem ghir f nefs l run, ya3ni ~5 sa3at men ba3d l montage.

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
- **Video 9:16 / 4:5:** jouj versions: 🖼 frame 9bel (video full 9:16, logo + `#rkn` l fo9 b dégradé navy, titre l t7t b animation, bla shadow) w mn ba3d 📱 l 9dima (zoom, panel b animation),
  kol wa7da b cover dyalha. Video 4:5 / 3:4 (machi 9:16): l bot kaysowl mor tanzil: ✂️ Crop (full) wla
  🖼 B cadre (video f l wost b fond mdbbel, b7al 16:9).
- **Logo:** l fo9 3la l imin, l video kamla.
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
