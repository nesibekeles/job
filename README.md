# İş Radarı

## Çalıştırma
Terminalde:

```bash
cd "/Users/nesibegulkeles/Desktop/2027 iş değiştirmece/jobfinder" && python3 server.py
```

Tarayıcıda http://localhost:8765 açılır. İlk seferde ya da her gün bir kez sağ üstten **İlanları güncelle**'ye bas.
İnternet yavaşsa 5–10 dakika sürebilir.

## Akış
1. **Keşfet:** kartı sağa kaydır (♥) ya da sola kaydır (✕) ve sebep seç. Tıklarsan detay açılır.
2. **Kısa liste:** beğendiklerin burada. “Paket hazırla” → Claude Code'da `paketleri hazırla` yaz.
3. Paket gelince kontrol et, ilandan başvur, durumu “Başvuruldu” yap.
4. **Elenenler:** otomatik elenenleri kontrol et. Yanlış elenen varsa kurtar.
5. **Öğrenme:** kaydırmalardan ne öğrendiğini gösterir.
6. **Ayarlar:** anahtar kelimeler, şehir ve maaş hedefleri, şirket listesi.

## Claude Code komutları
- `paketleri hazırla`: role özel CV, cover letter ve form cevapları
- `ilanları AI ile değerlendir`: en iyi ilanları okuyup sponsorluğu ve rol tipini düzeltir
- `şu ilanı ekle <link>`: LinkedIn ya da Google'daki tek bir ilanı ekler
- `yeni şirket ekle <şirket>`

## Canlı sürüm (GitHub Pages)
- Site: https://nesibekeles.github.io/Job/ (telefonda da çalışır; ana ekrana ekleyebilirsin)
- İlanlar her sabah 08:00'de (İstanbul) GitHub'da otomatik güncellenir. Elle güncellemek için sağ üstteki ↻ → “Run workflow”.
- Kaydırmaların o cihazın tarayıcısında saklanır. Cihaz değiştirirken: Ayarlar → Kararları indir / yükle.
- Ayarlar sekmesindeki linklerden JSON dosyalarını GitHub'da düzenle; kaydedince site yeniden puanlanır.
- Repo herkese açık (ücretsiz Pages için). CV, kararlar ve başvuru paketleri repoya **girmez** (.gitignore).
