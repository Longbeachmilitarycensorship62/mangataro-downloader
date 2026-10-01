<div align="right">

[English](README.md) · **فارسی** · [简体中文](README.zh.md)

# quicktunnel

یک سرور Xray با پروتکل **VLESS روی WebSocket** را پشت یک **Cloudflare Tunnel** اجرا می‌کند؛ به این ترتیب سروری که IP عمومی ندارد و هیچ پورت ورودی روی آن باز نیست، از طریق پورت `443` و روی آدرس `*.trycloudflare.com` (یا دامنهٔ خودتان) در دسترس قرار می‌گیرد.

همه چیز در مسیر `/usr/local/quicktunnel` نصب می‌شود، یک سرویس ثبت می‌گردد، و در پایان لینک `vless://` به همراه یک QR Code قابل اسکن در ترمینال چاپ می‌شود.

</div>

```
client ──TLS/WS:443──▶ Cloudflare edge ──▶ cloudflared ──▶ xray (127.0.0.1) ──▶ internet
```

<div align="right">

## نصب

با یک دستور، بدون نیاز به clone کردن مخزن:

</div>

```bash
bash <(curl -Ls https://raw.githubusercontent.com/hossinasaadi/quicktunnel/main/install.sh)
```

<div align="right">

به صورت پیش‌فرض تعاملی است: مود تونل، پورت‌ها، UUID، مسیر WebSocket، نام کانفیگ (remark) و heartbeat را می‌پرسد. مقدار فعلی هر گزینه به عنوان پیش‌فرض نمایش داده می‌شود، بنابراین می‌توانید با زدن Enter از همهٔ مراحل رد شوید.

برای نصب بدون پرسش، آرگومان‌ها را بعد از `--` اضافه کنید:

</div>

```bash
bash <(curl -Ls https://raw.githubusercontent.com/hossinasaadi/quicktunnel/main/install.sh) --yes
bash <(curl -Ls https://raw.githubusercontent.com/hossinasaadi/quicktunnel/main/install.sh) \
  --mode named --hostname proxy.example.com --tunnel-name xray --yes
```

| آرگومان | توضیح |
|---|---|
| `--yes` | بدون پرسش، با مقادیر پیش‌فرض |
| `--mode quick\|named` | مود تونل |
| `--hostname H` | نام میزبان عمومی (در مود `named`) |
| `--tunnel-name N` | نام تونل در cloudflared (در مود `named`) |
| `--port N` | پورت لوکالی که cloudflared به آن وصل می‌شود (پیش‌فرض `8080`) |
| `--socks-port N` | پورت SOCKS داخل کانفیگ کلاینت (پیش‌فرض `10808`) |
| `--uuid U` / `--ws-path P` | به جای تولید خودکار، مقدار دلخواه بدهید |
| `--remark R` | نام کانفیگ که در اپلیکیشن‌های کلاینت دیده می‌شود (پیش‌فرض `quicktunnel`) |
| `--transport T` | یکی از `ws` (پیش‌فرض)، `httpupgrade` یا `xhttp` (فقط در مود named) |
| `--heartbeat N` | فاصلهٔ ping روی WebSocket بر حسب ثانیه (پیش‌فرض `30`) |
| `--prefix DIR` | نصب در مسیری دیگر (پیش‌فرض `/usr/local/quicktunnel`) |
| `--no-service` | فقط فایل‌ها نصب شوند، بدون ساخت سرویس |

<div align="right">

نصب‌کننده فایل دانلودشدهٔ Xray را با مقدار `SHA2-256` منتشرشدهٔ خودش مقایسه می‌کند و در صورت مغایرت، نصب را متوقف می‌کند.

## مودها

**quick** — رایگان و بدون نیاز به حساب Cloudflare. نام میزبان به صورت تصادفی داده می‌شود و **با هر بار ری‌استارت عوض می‌شود**، بنابراین باید کانفیگ را هر بار دوباره در کلاینت وارد کنید. Cloudflare برای این تونل‌ها تضمین آپ‌تایم نمی‌دهد.

**named** — نام میزبان ثابت روی دامنه‌ای که از قبل در حساب Cloudflare شما موجود است. یک بار این مراحل را انجام دهید:

</div>

```bash
cloudflared tunnel login
cloudflared tunnel create xray
cloudflared tunnel route dns xray proxy.example.com
```

<div align="right">

سپس با `--mode named --hostname proxy.example.com --tunnel-name xray` نصب کنید. در این حالت لینک و QR Code بعد از ری‌استارت هم معتبر می‌مانند.

## مدیریت

</div>

```bash
quicktunnel-cli status         # وضعیت سرویس، مود، و نام میزبان فعلی
quicktunnel-cli qr             # QR Code لینک فعلی
quicktunnel-cli link           # لینک vless://
quicktunnel-cli link --full    # همان لینک، با sni و host نوشته‌شده
quicktunnel-cli client         # فایل JSON کانفیگ کلاینت
quicktunnel-cli log -f tunnel  # daemon | xray | tunnel | access | error
quicktunnel-cli restart        # در مود quick: نام میزبان جدید می‌گیرد
quicktunnel-cli reconfigure    # اجرای دوبارهٔ ویزارد تنظیمات
quicktunnel-cli update         # به‌روزرسانی xray و cloudflared
quicktunnel-cli uninstall
```

<div align="right">

بیشتر دستورها به `sudo` نیاز دارند، چون فایل کانفیگ حاوی اعتبارنامهٔ کلاینت است و با دسترسی `600` ذخیره می‌شود.

## ترنسپورت‌ها

Cloudflare انتخاب را محدود می‌کند، و **مهم است که از تونل quick استفاده کنید یا از دامنهٔ خودتان**:

</div>

| ترنسپورت | تونل quick | مود named (دامنهٔ خودتان) | دلیل |
|---|---|---|---|
| `ws` | **کار می‌کند** | **کار می‌کند** | آپگرید ۱۰۱ به یک مسیر خام که edge دست‌نخورده عبورش می‌دهد |
| `httpupgrade` | **کار می‌کند**\* | **کار می‌کند**\* | همان آپگرید، بدون فریم و ماسک WebSocket، پس سریع‌تر |
| `xhttp` | کار نمی‌کند | **کار می‌کند** (packet-up) | توضیح پایین |
| Reality/Vision، raw TCP، mKCP، QUIC | ممکن نیست | ممکن نیست | TLS در edge کلادفلر خاتمه می‌یابد |

<div align="right">

\* `httpupgrade` به نسخه‌ای از Xray نیاز دارد که اصلاح هدر `Sec-WebSocket-Key` را داشته باشد ([XTLS/Xray-core#6835](https://github.com/XTLS/Xray-core/pull/6835)). نسخه‌های قدیمی‌تر دست‌دادن ناقص می‌فرستند و Cloudflare با `500` پاسخ می‌دهد. ضمناً heartbeat ندارد، پس اتصال بیکار بعد از حدود ۱۲۶ ثانیه قطع می‌شود.

**چرا `xhttp` به دامنهٔ خودتان نیاز دارد.** تونل quick بدنهٔ پاسخ را تا زمانی که ۱۳۱۰۷۲ بایت جمع نشود نگه می‌دارد و نوشتن‌های کوچک را هرگز استریم نمی‌کند — حتی بعد از یک انفجار اولیه. این موضوع مسیر دانلود XHTTP را قفل می‌کند: چند کیلوبایت دست‌دادن TLS داخل بافر می‌ماند، پس ترافیک هیچ‌وقت به آستانه‌ای که بافر را خالی کند نمی‌رسد. یک دانلود ۵ مگابایتی از طریق تونل quick صفر بایت برگرداند. اما یک zone واقعی نوشتن‌های کوچک را بلافاصله استریم می‌کند (تکه‌هایی که هر ثانیه ارسال شدند با فاصلهٔ ۱ ثانیه رسیدند)، پس XHTTP آنجا کار می‌کند. فقط `packet-up` — چون `stream-up` و `stream-one` به بدنهٔ درخواست استریمی نیاز دارند که Cloudflare آن را بافر می‌کند.

**چرا Reality هرگز کار نمی‌کند.** Cloudflare با گواهی خودش TLS را خاتمه می‌دهد، پس دست‌دادن Reality هرگز به این سرور نمی‌رسد. نتیجهٔ تست: `remote error: tls: handshake failure` و سرور اصلاً هیچ اتصالی ندید. هیچ پورت یا تنظیمی این را تغییر نمی‌دهد.

سه تنظیم در کانفیگ‌های تولیدشده نقش کلیدی دارند:

- **`alpn: ["http/1.1"]`** (کلاینت) — در غیر این صورت Xray مقدار `h2` را هم پیشنهاد می‌دهد و اگر `h2` انتخاب شود، آپگرید WebSocket روی HTTP/1.1 خراب می‌شود.
- **`heartbeatPeriod: 30`** — Cloudflare اتصال‌های WebSocket بیکار را بعد از ۱۰۰ ثانیه با TCP RST و بدون close handshake قطع می‌کند. بدون ping، نشست‌های بیکار مثل SSH یا RDP بی‌صدا می‌میرند.
- **`sockopt.trustedXForwardedFor: ["CF-Connecting-IP"]`** (سرور) — ورودی این گزینه **نام هدرها** است، نه IP. بدون آن Xray برای هر اتصال یک هشدار ثبت می‌کند و IP همهٔ کلاینت‌ها را `127.0.0.1` می‌بیند.

از IP به‌دست‌آمده برای کنترل دسترسی استفاده نکنید: Cloudflare مقدار `X-Forwarded-For` ارسالی کلاینت را *به انتهای زنجیره اضافه* می‌کند و Xray اولین مقدار از سمت چپ را می‌خواند، پس قابل جعل است. برای لاگ گرفتن مشکلی ندارد.

## نکته دربارهٔ استفاده

در متن هشدار خود Cloudflare آمده است که تونل‌های بدون حساب کاربری هیچ تضمین آپ‌تایمی ندارند و Cloudflare این حق را برای خود محفوظ می‌داند که استفاده از آن‌ها را از نظر نقض شرایط سرویس بررسی کند. در مود `named` هم ترافیک به حساب کاربری و دامنهٔ خودتان گره می‌خورد. در هر دو حالت، آگاهانه تصمیم بگیرید.

</div>
