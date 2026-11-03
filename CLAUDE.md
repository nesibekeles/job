# Jobness – Claude Code çalışma notları

Nesibe Keleş'in yurtdışı marketing / growth / product marketing iş araması için kişisel araç.
Kullanıcı Türkçe konuşur; sohbet Türkçe. Web arayüzü, etiketler ve başvuru belgeleri İngilizce.

## Parçalar
- `jobfinder.py`: kariyer sitelerinden (Greenhouse, Lever, Ashby, SmartRecruiters, Workday, Amazon) ilan çeker, analiz eder → `data/jobs.json`
- `server.py`: http://localhost:8765 yerel sunucu. Puanlama, kurallar, öğrenme ve ayarlar tarayıcıda (`web/index.html`); sunucu uygulama durumunu `data/state.json`'a yansıtır (kararlar, kurallar, ağırlıklar, ayarlar).
- Canlı sürüm: GitHub Pages (https://nesibekeles.github.io/job/), her gün `.github/workflows/update.yml` ile güncellenir. Orada durum sadece tarayıcıda; kullanıcı “Yedeği indir” ile `jobness-yedek-*.json` (eski adı `pusula-yedek-*.json`) verir, aynı formatta.
- `config/*.json`: profil, şehir/maaş hedefleri, şirket listesi (kullanıcı arayüzden de düzenler)
- `voice.md`: yazı sesi ve CV uyarlama kuralları. **Paket hazırlamadan önce mutlaka oku.** Cover letter benchmark'ı: `samples/cover-letter-google-arts-culture.md` (git'e girmez).
- CV kaynağı: `private/resume_base.json` (yapılandırılmış, git'e girmez; telefon/e-posta içerir). Orijinali `../Nesibe Keles_Resume.pdf`.
- `packs.py`: `packs/<id>/pack.json` → tek sayfa PDF özgeçmiş (Chrome headless + Calibri, orijinal CV düzeni).

## Komut: "paketleri hazırla"
Kullanıcı ham markdown / .docx istemiyor: CV **sadece PDF**, geri kalan her şey uygulamadaki paket panelinde (checklist, düzenlenebilir cover letter, kopyalanabilir form cevapları, mülakat hazırlığı) gösterilir. Örnek: `packs/airbnb-8207342/pack.json`.
1. Kararları oku: `data/state.json` ya da kullanıcının verdiği `jobness-yedek-*.json` → `decisions` içinde `status == "Pack requested"` olan her ilan id'si için `data/jobs.json`'dan ilanı (açıklama dahil) oku.
2. `packs/<id>/pack.json` yaz (İngilizce): `job_id, company, title, location, apply_url, prepared_at, resume_file` (`"Nesibe Keles_CV_<Şirket>.pdf"`), `assessment` [{tone: warn|info|good, text}], `checklist` [metin], `resume` (sadece `resume_base.json`'dan farklı üst düzey alanlar: headline, profile, expertise, experience…; voice.md CV kuralları, uydurma yok), `cover_letter` {greeting, paragraphs[], signoff, name} (benchmark `samples/cover-letter-google-arts-culture.md` + voice.md yapısı ve yasak listesi; sponsorluk voice.md kuralına göre), `answers` [{q, a, note?}] (salary expectation = şehir hedefi yerel para biriminde ya da ilan aralığı; boş bırakılacaklar `a: ""` + note), `fit` [{need, you}], `gaps` [metin], `questions` [metin].
3. `python3 packs.py <id>` çalıştır. "1 page" demeli; uzunsa `resume` metnini kısalt, tekrar üret. PDF'i `sips -s format png` ile görsele çevirip bak.
4. Cover letter ve cevaplarda yasak listesini tara; kalırsa düzelt.
5. State dosyasında kararın `status`'ünü "Pack ready" yap, `updated_at`'i şimdiye çek (yerel sunucuda arayüz bunu alır; yedek dosyasıysa güncellenmiş dosyayı kullanıcıya geri ver).
Kullanıcının panelde yaptığı düzenlemeler ve tikler `state.packs[<id>]` içinde ({checks, prep, answers, cover}); paketi yeniden üretirken bunları ezme.

Başvuruyu **asla otomatik gönderme**. Hesap açma ve şifre girme de yok. Kullanıcı paketi gözden geçirip kendisi başvurur.

## Komut: "ilanları AI ile değerlendir"
Skoru en yüksek ~30 karar verilmemiş ilanı oku. Regex'in kaçırdığını düzelt: sponsorluk gerçekten var mı/yok mu, rol stratejik mi operasyonel mi, gizli dil şartı. Sonucu `data/ai_notes.json`'a yaz: `{ "<id>": {"sponsorship": "yes|no|unknown", "role_type": "strategic|mixed|operational", "filtered": null | "sebep", "summary": "1-2 sentence English summary", "tags": [{"color":"green|red|yellow","label":"..."}], "scene": {"critic":0-1, "seed":0-1, "dig":0-1, "cast":0-1, "crew":-1-1, "novel":-1-1, "ritual":0-1}, "scene_note": "Bir günün nasıl geçeceğine dair 1 cümle (English)"} }`. Sonra `python3 jobfinder.py rescore`.

### Scene engine (sahne motoru)
Nesibe'nin hayal ettiği iş bir yaşam tarzı: küçük, samimi, gösterişsiz ekip; küçük ya da genel bir fikirden başlayıp üstüne inşa etmek ve derinleşmek; sürekli beyin fırtınası; sonuçları gözden geçirip geri bildirim vermek; hep yeni keşifler; gelenekler için “özel bölümler”. Tarayıcı bunu 7 sahnede (critic, seed, dig, cast, crew, novel, ritual) ifade cümlelerinden puanlar (Puanlama → Scene engine'de düzenlenebilir). AI değerlendirmesinde `scene` değerlerini ilanı gerçekten okuyarak ver: kelime değil, işin günlük dokusu. Büyük matris şirket, “rockstar/hustle” dili, raporlama ağırlıklı iş → düşük ya da negatif. Kanıt yoksa o anahtarı hiç yazma (regex kalır).

## Komut: "şu ilanı ekle <link>"
Linki Chrome'da (salt okuma) ya da web-fetch ile aç, metni al ve `data/manual_jobs.json`'a `jobfinder.job(...)` formatında ekle (`"manual": true`), sonra `python3 jobfinder.py rescore`. LinkedIn'de toplu tarama yapma; sadece kullanıcının verdiği tek ilanlar.

## Telefondan ilan ve şehir ekleme
- Uygulamada **Add a job** (Discover'daki +, Profile → Add a job): link yapıştırılır. Mac'te `/api/add-url` anında okur; telefonda "Add job" başlıklı GitHub issue açılır, `.github/workflows/add-job.yml` okur, ekler, kapatır, siteyi yeniden kurar. Elle: `python3 jobfinder.py add-url <link> [metin-dosyası]`.
- Okunan kaynaklar: LinkedIn'in herkese açık ilan sayfası (tek ilan, tarama yok), Greenhouse/Lever/Ashby API'leri, diğer sitelerde schema.org JobPosting. Okunamazsa yapıştırılan metin kullanılır.
- **Add a city** (Preferences → Cities): Mac'te `/api/city` `config/cities.json`'a ekler ve yayınlar; telefonda "Add city: X" issue'su. Elle: `python3 jobfinder.py add-city <şehir> [ülke] [öncelik] [hedef €/yıl]`.
- İstanbul `home: true`: vize gerekmez. Lever'da şehir yazmayan şirketlere `base` alanı (ör. Peak Games → Istanbul).

## Komut: "yeni şirket ekle X"
Hangi ATS'i kullandığını bul (kariyer sayfası linkinden: boards.greenhouse.io, jobs.lever.co, jobs.ashbyhq.com, *.myworkdayjobs.com, jobs.smartrecruiters.com), API'nin cevap verdiğini doğrula, `config/companies.json`'a ekle. Okunamıyorsa watchlist'e koy.

## Her yeni özellik ve değişiklikte: 360° kontrol (Nesibe'nin kuralı)
Bir şeyi "eklendi" diye teslim etmeden önce kullanıcının gözünden bütün döngüyü düşün ve dene:
- **Yaşam döngüsü:** oluştur · gör · düzenle · sil · geri al (undo) · boş hâl · çok fazla öğe hâli. Eklenen her şey düzenlenebilir ve silinebilir olmalı.
- **Girdi:** açık bir kaydet/ekle butonu (Enter tek başına yayınlamasın), iptal, yanlışlıkla dokunmaya karşı onay ya da geri alma.
- **Bağlantılar:** öğe ilgili yere bağlanabiliyor mu (ilan, paket, sayfa, link)? Otomatik üretilen metinler (alt yazı, etiket) düzenlenebiliyor mu?
- **Sayılar ve filtreler:** her sayı ekrandaki listeyle birebir tutuyor mu? Filtre seçiliyken boş liste ne diyor?
- **Ekranlar:** 375 px telefon ve masaüstü; taşan/kırpılan yazı, tooltip ve popup ekrana sığıyor mu, dokunma alanları yeterli mi?
- **Temalar:** Casual, Businessman, Prefer not to disclose; bir temada yapılan font/renk değişikliği diğerlerini bozmasın (temaların fontları sabit).
- **Veri:** güncellemeler ve canlı site senkronu kullanıcı verisini asla silmesin; telefon ve Mac verisi birleşir.
- **Tutarlılık ve görünüm:** benchmark'lara bak (Apple Wallet, iOS, modern SaaS); mevcut tasarım diliyle aynı, profesyonel görünmeli. Ekran görüntüsü alıp gerçekten bak; "çalışıyor" yetmez, "iyi görünüyor ve anlaşılır" olmalı.
- **Tarayıcı popup'ı yok:** confirm/alert yerine uygulamanın kendi diyalogları.
- **Eski özellikler kaybolmaz:** yeni bir yayın daha önce istenmiş bir özelliği silmez ya da bozmaz; ancak Nesibe söylediyse ya da yeni sürüm onu gerçekten daha iyi yapıyorsa değişir (ve bu ona söylenir). Büyük değişiklikten sonra git HEAD ile karşılaştır: silinen fonksiyon, `data-*` handler'ı, buton var mı? Telefon ↔ Mac birleştirmesi (`mergeShared`) yeni bir alan eklenince o alanı da korumalı.
- **Uygulama içi görevler elle tiklenmez:** challenge, test, karar, paket, başvuru gibi Jobness'te yapılan to-do'lar iş gerçekten yapılınca kendiliğinden tiklenir; elle tiklenince nerede yapılacağını söyleyen uyarı çıkar.
