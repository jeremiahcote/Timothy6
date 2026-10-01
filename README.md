# Timothy6

Blocks pornography and adult content on an iPhone, and can only be turned on or
off from your computer over USB.

## How it works

`blocker.py` installs a configuration profile containing:

- **Encrypted DNS filter** (CleanBrowsing Adult by default) that the phone
  cannot switch off. Applies on Wi-Fi and cellular, in every app.
- **Apple's built-in adult website filter** as a second layer.
- **Restrictions**: no VPN apps, no iCloud Private Relay, no explicit
  media, no installing other profiles, no "Erase All Content and Settings".

The profile is marked non-removable. iOS only honours that on a **supervised**
iPhone, and only the computer holding the supervision key ("keybag") can
install or remove it. The keybag is stored in `%LOCALAPPDATA%\Timothy6\`,
never on the phone.

## Requirements

- Python 3.9+
- Windows: the **Apple Devices** app (or iTunes) for the USB driver
- `pip install -r requirements.txt`

## Usage

Plug the phone in, unlock it, tap **Trust**.

```
python blocker.py setup      # one-time: supervise the phone
python blocker.py enable
python blocker.py disable
python blocker.py status
python blocker.py export out.mobileconfig   # inspect the profile
```

### If setup fails

Apple normally only lets a phone become supervised while it is freshly erased.
If `setup` is refused on a phone that is already in use:

1. Back the phone up (iCloud or the Apple Devices app).
2. Turn off Find My, then erase it (Settings > General > Transfer or Reset).
3. Leave it on the "Hello" screen, plug it in, run `python blocker.py setup`.
4. Finish setup on the phone and restore your backup.
5. Check Settings > General > About says "This iPhone is supervised". If the
   restore removed supervision, set the phone up as new instead.

### Supervising without erasing (experimental)

`python supervise_backup.py` backs the phone up, edits the supervision setting
inside the backup and restores it, so the phone restarts once and keeps its
data. Run `python blocker.py setup` first to create the keybag. It currently
only supports the iOS 5-9 backup format and has been tested on one iPhone 5
running iOS 8.4. It does not work on current iPhones yet.

### Instagram without Reels or Search

`instagram/instagram-clean.user.js` is a userscript for the Userscripts Safari
extension. It hides the Reels feed and Search/Explore on instagram.com. Block
the Instagram app and use the website in Safari.

## Configuration

Copy any keys from `DEFAULTS` in `blocker.py` into a `config.json` next to it,
then run `enable` again. For example, to pick the blocked apps, add a website
and also remove the App Store:

```json
{
  "blocked_apps": ["reddit", "twitter", "tiktok"],
  "blocked_websites": ["example.com"],
  "block_app_store": true
}
```

`blocked_apps` takes the names in `KNOWN_APPS` (which also block that app's
website) or any raw bundle ID.

## Limits

- DNS filtering blocks whole sites. Adult content inside otherwise-allowed
  apps (X, Telegram, etc.) is not filtered; remove those apps or lower
  `max_app_rating`.
- Restoring the phone in recovery mode from a computer wipes everything,
  including the filter.
- If you lose the keybag, the only way to remove the filter is to erase the
  phone. Back it up somewhere the phone cannot reach.

## License

MIT
