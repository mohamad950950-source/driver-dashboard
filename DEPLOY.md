# 🚀 Deploy Guide — Driver Dashboard to Netlify

## 1️⃣ إنشاء موقع Netlify

1. افتح: https://app.netlify.com
2. سجل دخول بـ **GitHub**
3. اضغط **Add new site → Import existing project → Deploy with GitHub**
4. اختر **driver-dashboard** من القائمة

## 2️⃣ إعدادات الـ Deploy

- **Build command**: (leave empty)
- **Publish directory**: `.`
- اضغط **Deploy**

## 3️⃣ إضافة قاعدة البيانات (Supabase)

1. افتح https://supabase.com
2. سجل دخول بـ GitHub
3. اضغط **New Project**
   - Name: `driver-dashboard`
   - Database Password: (اختر واحفظه)
4. استنى 2 دقيقة
5. روح على **Project Settings → Database → Connection string**
6. **انسخ الـ URI** (يبدأ بـ `postgresql://postgres:****@db.xxx.supabase.co:5432/postgres`)

## 4️⃣ ربط الـ DATABASE_URL

1. في Netlify Dashboard:
   - **Site settings → Environment variables**
   - Add variable:
     - Key: `DATABASE_URL`
     - Value: (انسخ URI من Supabase)
2. **Deploy → Trigger deploy → Deploy site**

بعد دقيقتين، التطبيق شغال 🎉

## أو بديل أسهل — استخدم الـ deploy button

فتح الرابط ده:
```
https://app.netlify.com/start/deploy?repository=https://github.com/mohamad950950-source/driver-dashboard
```
