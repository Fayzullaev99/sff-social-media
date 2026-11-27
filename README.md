# 🤖 Social Agent: ijtimoiy tarmoqlar uchun AI agent

Bu agent Telegram akkauntingizni boshqaradi:
- ruxsat berilgan chatlarga avtomatik javob beradi;
- kanalga post tayyorlaydi va joylaydi;
- izohlarga javob beradi.

Bilim bazasida javob topa olmasa, savolni sizga yuboradi. Siz bergan javobni o'rganib, bazaga qo'shib boradi.

> **Pul bilan bog'liq har qanday amal** va **har bir post** faqat siz tasdiqlaganingizdan keyin bajariladi.

---

## ⚡ O'rnatish (Windows)

```powershell
cd f:\other\social-agent
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env      # keyin .env faylini to'ldiring
```

### 1. Kalitlarni oling va `.env` ga yozing

| Nima | Qayerdan | `.env` dagi nomi |
|---|---|---|
| Gemini API kaliti | https://aistudio.google.com/apikey | `GEMINI_API_KEY` |
| Telegram API | https://my.telegram.org → *API development tools* | `TG_API_ID`, `TG_API_HASH` |
| Admin-bot tokeni | Telegram'da **@BotFather** → `/newbot` | `ADMIN_BOT_TOKEN` |
| Sizning Telegram ID raqamingiz | **@userinfobot** | `ADMIN_IDS` |
| Dashboard paroli | o'zingiz o'ylab toping | `DASHBOARD_PASSWORD` |

### 2. Telegram akkauntga bir marta kiring

```powershell
.venv\Scripts\python login.py
```

Telefon raqamingizni, Telegram yuborgan kodni va (yoqilgan bo'lsa) 2FA parolni kiriting. Sessiya `data/` papkasida saqlanadi.

> ⚠️ `data/` papkasini va `.env` faylini **hech kimga bermang**: ular orqali akkauntingizga kirish mumkin.

### 3. Agentni ishga tushiring

```powershell
.venv\Scripts\python run.py
```

Dashboard'ni brauzerda oching: **http://127.0.0.1:8080** (login: `admin`, parol: `.env` dagi `DASHBOARD_PASSWORD`).

Admin-botingizga Telegram'da `/start` yozing.

---

## 🚀 Birinchi qadamlar

1. **Bilim bazasi:** kompaniya haqidagi ma'lumotlarni, narxlarni, FAQ'ni va xizmatlarni yuklang (PDF, DOCX, TXT yoki sayt havolasi). Faylni admin-botga yuborsangiz ham bazaga qo'shiladi.
2. **Sinov:** agent qanday javob berishini xavfsiz tekshirib ko'ring (bu yerdagi xabarlar hech kimga yuborilmaydi).
3. **Sozlamalar:** agent kim nomidan va qanday uslubda yozishini belgilang.
4. **Chatlar → Telegram dialoglari:** agent javob beradigan kontakt, guruh va kanallarni yoqing.
   - **⚡ Avto:** agent darhol javob beradi.
   - **✋ Tasdiq:** javob avval admin-botga tasdiqlash uchun keladi.
   - Kanalga ruxsat bersangiz, uning izohlar guruhi ham avtomatik qo'shiladi.
5. **Kontent:** "AI bilan yozish" tugmasini bossangiz, agent post tayyorlaydi. Postni dashboard'da yoki admin-botda tasdiqlaysiz, keyin u kanalga joylanadi.

## 🧠 Agent qanday ishlaydi

| Holat | Agent nima qiladi |
|---|---|
| Ruxsat berilgan chatga xabar keldi | Bir necha soniya kutadi (ketma-ket xabarlarni yig'ish uchun), bazadan javob qidiradi, "yozmoqda..." holatini ko'rsatib javob beradi |
| Mijoz ruscha, inglizcha va h.k. yozdi | Shu tilda javob beradi |
| Bazada javob yo'q | Mijozga "aniqlab, javob beraman" deb yozadi va **sizga ❓ xabar yuboradi** |
| Siz admin-botda ❓ xabariga reply qildingiz | Javobingizni mijozga yetkazadi va bazaga qo'shadi (keyingi safar o'zi javob beradi) |
| Mijoz chegirma, pul yoki uchrashuv so'radi | O'zi va'da bermaydi, sizdan so'raydi |
| Siz chatga o'zingiz yozdingiz | Agent bu chatda 10 daqiqa jim turadi |
| Guruhda | Faqat sizga murojaat qilinganda (mention/reply) yoki kalit so'z uchraganda javob beradi |
| Kanal izohi | Qisqa va xushmuomala javob beradi, spamga javob bermaydi |

## 🛡 Xavfsizlik

- Agent faqat **oq ro'yxatdagi** (siz ruxsat bergan) chatlarda ishlaydi.
- Tezlik cheklovi bor (daqiqasiga 20 tagacha javob). Bu Telegram akkauntingizni bloklanishdan himoya qiladi.
- Pul talab qiladigan amallar kod darajasida bloklangan: inson tasdig'isiz bajarilmaydi (`tests/test_core.py` da tekshirilgan).
- Kimdir jiddiy "sen botmisan?" deb so'rasa, agent buni inkor qilmaydi (sozlamalarda o'chirib qo'yish mumkin).

## 🗺 Yo'l xaritasi

- [x] **1-bosqich:** yadro, Telegram avtojavob, bilim bazasi, admin-bot, dashboard
- [x] **2-bosqich:** kanal postlari (tasdiq orqali), rejalashtirish, izohlarga javob
- [x] **3-bosqich:** video fabrikasi (ssenariy → `edge-tts` ovoz → stok/kinetik/Veo/HeyGen montaj), YouTube va Instagram'ga joylash, izohlarga tiliga mos avtojavob
- [x] **4-bosqich:** analitika, sifat reytingi va o'z-o'zini to'g'irlash, targetolog (Meta Ads, Google Ads; har bir pul sarfi kod darajasida majburiy tasdiq bilan)

## 📺 YouTube, 📸 Instagram va 🎯 Targetolog ulash

1. **YouTube**: Google Cloud Console → *YouTube Data API v3* ni yoqing → OAuth Desktop JSON faylini `data/youtube_client_secret.json` ga qo'ying va bir marta ishga tushiring:
   ```powershell
   .venv\Scripts\python youtube_auth.py
   ```
2. **Instagram**: Business/Creator akkauntni Facebook Page'ga ulang, `.env` ga `IG_ACCESS_TOKEN`, `IG_ACCOUNT_ID` va Reels yuklash uchun `PUBLIC_MEDIA_BASE_URL` (masalan VPS HTTPS domeningiz) yozing.
3. **Targetolog (Meta Ads / Google Ads)**: `.env` ga reklama kalitlarini kiriting. Kalitlar kiritilmagan bo'lsa ham Targetolog strategiya, auditoriya va reklama matnlarini tuzib beradi.
4. **24/7 VPS serverga ko'chirish (Docker)**:
   ```bash
   docker compose up -d --build
   ```

## 🧪 Testlar

```powershell
.venv\Scripts\python -m pytest -q
```

## 📁 Tuzilma

```
run.py                     # hammasini ishga tushiradi
login.py                   # bir martalik Telegram login
config/settings.yaml       # standart sozlamalar
app/core/                  # brain (Gemini), policy, holat, repozitoriylar
app/knowledge/store.py     # bilim bazasi (RAG, vektor qidiruv)
app/channels/              # Telegram userbot
app/admin/bot.py           # admin-bot (tasdiqlar, savollar)
app/approvals/service.py   # tasdiqlash navbati va pul himoyasi
app/content/posts.py       # post yaratish va joylash
app/web/                   # dashboard (FastAPI + HTML/CSS/JS)
```
