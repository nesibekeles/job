# İş Radarı – Claude Code çalışma notları

Nesibe Keleş'in yurtdışı marketing / growth / product marketing iş araması için kişisel araç.
Kullanıcı Türkçe konuşur; arayüz ve cevaplar Türkçe, başvuru belgeleri İngilizce.

## Parçalar
- `jobfinder.py`: kariyer sitelerinden (Greenhouse, Lever, Ashby, SmartRecruiters, Workday, Amazon) ilan çeker, analiz eder → `data/jobs.json`
- `server.py`: http://localhost:8765 arayüzü ve API. Kaydırmalar `data/decisions.json`, öğrenme `jobfinder.learn()`
- `config/*.json`: profil, şehir/maaş hedefleri, şirket listesi (kullanıcı arayüzden de düzenler)
- `voice.md`: yazı sesi ve CV uyarlama kuralları. **Paket hazırlamadan önce mutlaka oku.**
- CV kaynağı: `../Nesibe Keles_Resume.docx` ve `.pdf`

## Komut: "paketleri hazırla"
1. `data/pack_queue.json` içindeki her ilan id'si için `data/jobs.json`'dan ilanı (açıklama dahil) oku.
2. `packs/<id>/` klasörüne yaz:
   - `cv.docx`: `../Nesibe Keles_Resume.docx`'tan türet (docx skill), voice.md'deki CV kurallarına göre. Uydurma yok. Ayrıca `cv.pdf`.
   - `cover_letter.md`: voice.md yapısı ve yasak listesiyle. Taşınma ve sponsorluk ihtiyacını tek cümleyle dürüstçe söyle.
   - `answers.md`: sık form soruları (Why us, Why this role, salary expectation = şehrin `gross_target_eur` değeri yerel para biriminde, notice period, right to work: "I'd require visa sponsorship"), ilan linki.
   - `notes.md`: eşleşen noktalar, boşluklar (gaps), mülakatta beklenecek sorular.
3. Bittikten sonra `data/decisions.json`'da ilgili kaydın `status`'ünü "Paket hazır" yap ve id'yi kuyruktan çıkar.
4. Her cover letter'ı yazdıktan sonra yasak listesini tara; kalırsa düzelt.

Başvuruyu **asla otomatik gönderme**. Hesap açma ve şifre girme de yok. Kullanıcı paketi gözden geçirip kendisi başvurur.

## Komut: "ilanları AI ile değerlendir"
Skoru en yüksek ~30 karar verilmemiş ilanı oku. Regex'in kaçırdığını düzelt: sponsorluk gerçekten var mı/yok mu, rol stratejik mi operasyonel mi, gizli dil şartı. Sonucu `data/ai_notes.json`'a yaz: `{ "<id>": {"sponsorship": "yes|no|unknown", "role_type": "stratejik|karma|operasyonel", "filtered": null | "sebep", "summary": "1-2 cümle Türkçe özet", "tags": [{"color":"green|red|yellow","label":"..."}]} }`. Sonra `python3 jobfinder.py rescore`.

## Komut: "şu ilanı ekle <link>"
Linki Chrome'da (salt okuma) ya da web-fetch ile aç, metni al ve `data/manual_jobs.json`'a `jobfinder.job(...)` formatında ekle (`"manual": true`), sonra `python3 jobfinder.py rescore`. LinkedIn'de toplu tarama yapma; sadece kullanıcının verdiği tek ilanlar.

## Komut: "yeni şirket ekle X"
Hangi ATS'i kullandığını bul (kariyer sayfası linkinden: boards.greenhouse.io, jobs.lever.co, jobs.ashbyhq.com, *.myworkdayjobs.com, jobs.smartrecruiters.com), API'nin cevap verdiğini doğrula, `config/companies.json`'a ekle. Okunamıyorsa watchlist'e koy.
