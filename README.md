## Preview

![preview](https://i.imgur.com/NgbOa6J.png)

## File Konfigurasi yang Diperlukan

### 1. `config/spotify.json`

File ini berisi kredensial API Spotify Anda. Buat file di lokasi `config/spotify.json` dengan struktur berikut:

```json
{
  "client_id": "YOUR_SPOTIFY_CLIENT_ID",
  "client_secret": "YOUR_SPOTIFY_CLIENT_SECRET"
}
```

#### Cara mendapatkan kredensial API Spotify:

1. Kunjungi [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Klik "CREATE AN APP"
3. Masukkan nama aplikasi dan deskripsi
4. Setelah dibuat, klik pada aplikasi Anda
5. Salin "Client ID" dan "Client Secret"
6. Buat file `config/spotify.json` dengan nilai-nilai tersebut

### 2. `config/headers_auth.json` (Direkomendasikan untuk YouTube Music)

File ini berisi header otentikasi YouTube Music. Ini adalah metode yang paling dapat diandalkan untuk akses YouTube Music.

#### Cara mendapatkan header YouTube Music:

1. Buka browser Anda dan kunjungi [YouTube Music](https://music.youtube.com)
2. Masuk ke akun Google Anda
3. Tekan F12 untuk membuka Developer Tools
4. Pergi ke tab Network
5. Muat ulang halaman
6. Cari permintaan apa pun ke `music.youtube.com` (klik salah satu jika perlu)
7. Pergi ke tab Headers
8. Temukan bagian "Request Headers"
9. Salin seluruh objek header (termasuk otorisasi, cookie, dll.)
10. Buat `config/headers_auth.json` dengan header berikut:

```json
{
  "authorization": "YOUR_AUTHORIZATION_HEADER",
  "cookie": "YOUR_COOKIE_VALUE",
  "x-goog-authuser": "0",
  "x-origin": "https://music.youtube.com"
}
```

### 3. `config/cookies.txt` (Alternatif untuk YouTube Music)

Ini adalah metode otentikasi alternatif menggunakan cookie browser.

#### Cara membuat cookies.txt:

1. Instal ekstensi browser "Cookie Editor"
2. Kunjungi [YouTube Music](https://music.youtube.com) dan putar lagu apa pun
3. Buka ekstensi Cookie Editor
4. Klik "Export" dan pilih "cURL format"
5. Simpan konten ke `config/cookies.txt`

Atau Anda bisa membuatnya secara manual dengan cookie penting:

```
# Netscape HTTP Cookie File
.music.youtube.com	TRUE	/	FALSE	2147483647	SID	"your_sid_value_here"
.music.youtube.com	TRUE	/	FALSE	2147483647	HSID	"your_hsid_value_here"
.music.youtube.com	TRUE	/	FALSE	2147483647	SSID	"your ssid_value_here"
.music.youtube.com	TRUE	/	FALSE	2147483647	APISID	"your_apisid_value_here"
.music.youtube.com	TRUE	/	FALSE	2147483647	SAPISID	"your_sapisid_value_here"
```

## Metode Otentikasi YouTube Music Alternatif

Jika Anda tidak ingin menggunakan header atau cookie, Anda juga dapat melakukan otentikasi menggunakan OAuth2:

### Metode OAuth2

Buat file `config/ytmusic.json` dengan kredensial OAuth:

```json
{
  "oauth_credentials": {
    "access_token": "your_access_token",
    "token_type": "Bearer",
    "expires_in": 3600,
    "refresh_token": "your_refresh_token",
    "scope": "..."
  }
}
```

## Struktur File

```
config/
├── spotify.json
├── headers_auth.json (direkomendasikan)
# ATAU
├── cookies.txt (alternatif)
# ATAU
├── ytmusic.json (alternatif)
```
