# Jobness – Claude Code çalışma notları

Nesibe Keleş'in yurtdışı marketing / growth / product marketing iş araması için kişisel araç.
Kullanıcı Türkçe konuşur; sohbet Türkçe. Web arayüzü, etiketler ve başvuru belgeleri İngilizce.

## Parçalar
- `jobfinder.py`: kariyer sitelerinden (Greenhouse, Lever, Ashby, SmartRecruiters, Workday, Amazon) ilan çeker, analiz eder → `data/jobs.json`
- `server.py`: http://localhost:8765 yerel sunucu. Puanlama, kurallar, öğrenme ve ayarlar tarayıcıda (`web/index.html`); sunucu uygulama durumunu `data/state.json`'a yansıtır (kararlar, kurallar, ağırlıklar, ayarlar).
- Canlı sürüm: GitHub Pages (https://nesibekeles.github.io/job/), her gün `.github/workflows/update.yml` ile güncellenir. Orada durum sadece tarayıcıda; kullanıcı “Yedeği indir” ile `jobness-yedek-*.json` (eski adı `pusula-yedek-*.json`) verir, aynı formatta.
- `config/*.json`: profil, şehir/maaş hedefleri, şirket listesi (kullanıcı arayüzden de düzenler)
- `voice.md`: yazı sesi ve CV uyarlama kuralları. **Paket hazırlamadan önce mutlaka oku.**
- CV kaynağı: `private/resume_base.json` (yapılandırılmış, git'e girmez; telefon/e-posta içerir). Orijinali `../Nesibe Keles_Resume.pdf`.
- `packs.py`: `packs/<id>/pack.json` → tek sayfa PDF özgeçmiş (Chrome headless + Calibri, orijinal CV düzeni).

## Komut: "paketleri hazırla"
Kullanıcı ham markdown / .docx istemiyor: CV **sadece PDF**, geri kalan her şey uygulamadaki paket panelinde (checklist, düzenlenebilir cover letter, kopyalanabilir form cevapları, mülakat hazırlığı) gösterilir. Örnek: `packs/airbnb-8207342/pack.json`.
1. Kararları oku: `data/state.json` ya da kullanıcının verdiği `jobness-yedek-*.json` → `decisions` içinde `status == "Pack requested"` olan her ilan id'si için `data/jobs.json`'dan ilanı (açıklama dahil) oku.
2. `packs/<id>/pack.json` yaz (İngilizce): `job_id, company, title, location, apply_url, prepared_at, resume_file` (`"Nesibe Keles_CV_<Şirket>.pdf"`), `assessment` [{tone: warn|info|good, text}], `checklist` [metin], `resume` (sadece `resume_base.json`'dan farklı üst düzey alanlar: headline, profile, expertise, experience…; voice.md CV kuralları, uydurma yok), `cover_letter` {greeting, paragraphs[], signoff, name} (voice.md yapısı + yasak listesi; taşınma ve sponsorluk tek cümle), `answers` [{q, a, note?}] (salary expectation = şehir hedefi yerel para biriminde ya da ilan aralığı; boş bırakılacaklar `a: ""` + note), `fit` [{need, you}], `gaps` [metin], `questions` [metin].
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

## Komut: "yeni şirket ekle X"
Hangi ATS'i kullandığını bul (kariyer sayfası linkinden: boards.greenhouse.io, jobs.lever.co, jobs.ashbyhq.com, *.myworkdayjobs.com, jobs.smartrecruiters.com), API'nin cevap verdiğini doğrula, `config/companies.json`'a ekle. Okunamıyorsa watchlist'e koy.
