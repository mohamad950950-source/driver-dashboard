# Driver Dashboard 🚘
### متتبع أرباح السواقين — Revenue Tracker for Drivers

نظام تحليلي للسواقين: Connect حسابات Uber/Didi/InDrive، تتبع البنزين والصيانة، تقارير أرباح، وتقسيم مع المالك.

## 🚀 التشغيل السريع

```bash
cd C:\Users\shafee\Downloads\driver-dashboard
uv run python app.py
```

ثم افتح **http://localhost:8000**

## 🌐 المشاركة مع صاحبك

```bash
ssh -R 80:localhost:8000 serveo.net
```

يطلعلك رابط مثل: `https://xxxx.serveousercontent.com` — أبعته لصاحبك.

## 📱 الدخول (Dev Mode)

مفيش يوزرنيم ولا باسورد — اضغط بس على الزر:
- **D** → سواق (بيروح /driver-connect)
- **O** → صاحب عربية (بيروح /owner-dashboard)

## 🗂️ هيكل المشروع

```
driver-dashboard/
├── app.py              ← الباك إند الرئيسي (FastAPI)
├── translations.py     ← كل الترجمة عربي/إنجليزي
├── requirements.txt    ← المكتبات المطلوبة
├── start.bat           ← ملف تشغيل
├── templates/          ← 24 قالب HTML (Jinja2)
│   ├── base.html       ← القاعدة (sidebar + mobile nav)
│   ├── login.html      ← صفحة الدخول (Dev Mode)
│   ├── driver_connect.html  ← الرئيسية (6 أزرار)
│   ├── driver_dashboard.html  ← تقرير كامل
│   ├── owner_dashboard.html  ← لوحة المالك
│   ├── trips.html       ← المشاوير
│   ├── expenses.html    ← المصروفات
│   ├── fuel.html        ← البنزين
│   ├── maintenance.html ← الصيانة
│   ├── settings.html    ← الإعدادات
│   ├── reports.html     ← التقارير
│   ├── accounts.html    ← الحسابات
│   ├── drivers.html     ← السواقين (للمالك)
│   ├── verify.html      ← توثيق المستندات
│   ├── oauth_*.html     ← صفحات Connect (Uber/Didi/InDrive)
│   └── register_*.html  ← صفحات التسجيل
├── data/                ← قاعدة البيانات (SQLite)
└── uploads/             ← الصور المرفوعة
```

## ⚙️ التقنيات

- **FastAPI** 0.133.1 — باك إند سريع
- **Jinja2** 3.1.6 — قوالب HTML
- **SQLite** — داتابيز خفيفة (مفيش setup)
- **Chart.js** — رسوم بيانية
- **uv** — مدير حزم بايثون

## 🌐 اللغات

- العربي (RTL) — افتراضي
- English (LTR) — switc من الإعدادات
