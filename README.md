# LocatorSync

Vue.js uygulamalarındaki Robot Framework test locator'larını analiz eden, kırık/kırılgan locator'ları tespit eden, otomatik düzelten ve Vue bileşenlerine `data-test` attribute'u ekleyen Python aracı.

---

## Ne İşe Yarar?

Vue bileşenleri değiştikçe Robot Framework test locator'ları (CSS, XPath, ID) bozulabilir. LocatorSync:

- Vue dosyalarındaki `data-test` eksikliklerini tespit eder
- Her locator'a 0–100 arası bir **stabilite skoru** verir (RF locator hiyerarşisine göre)
- Robot Framework testlerinde hangi locator'ların kırıldığını bulur
- Kırık locator'lar için **otomatik düzeltme** önerileri üretir ve uygular
- Vue bileşenlerine **otomatik `data-test` attribute ekler** (id varsa id değerini kullanır)
- Web arayüzü ile **tüm ekip** aynı anda kullanabilir

---

## Proje Yapısı

```
vue-test-healer/
│
├── configs/                    # Yapılandırma katmanı
│   └── AppConfig.py            # YAML veya dict ile yüklenebilir config
│
├── models/                     # Veri modelleri (dataclass)
│   ├── VueElement.py           # Vue element temsili
│   ├── RobotLocator.py         # Robot locator + ExtractionResult
│   └── AnalysisResult.py       # Audit, Match, Heal sonuç modelleri
│
├── enums/                      # Sabit değerler
│   ├── Severity.py             # critical / warning / info
│   ├── Confidence.py           # high / medium / low
│   └── StabilityLevel.py       # YUKSEK / ORTA / DUSUK / KRITIK
│
├── core/                       # İş mantığı katmanı (domain bazlı)
│   ├── scanner/
│   │   └── VueScanner.py       # .vue dosyalarını tarar, VueElement üretir
│   ├── analyzer/
│   │   ├── StabilityScorer.py  # Locator/element kırılganlık skoru
│   │   ├── LocatorExtractor.py # .robot dosyalarından locator çıkarır
│   │   ├── ChangeMatcher.py    # Vue vs Robot çapraz eşleştirme
│   │   └── VueDiffAnalyzer.py  # Eski/yeni Vue snapshot karşılaştırması
│   ├── auditor/
│   │   └── DataTestAuditor.py  # data-test kapsama denetimi
│   ├── healer/
│   │   └── HealerEngine.py     # Kırık locator için öneri + patch üretimi
│   └── patcher/
│       └── VuePatcher.py       # Vue dosyalarına data-test attribute ekler
│
├── services/                   # Yatay kesim servisleri
│   └── ReportService.py        # CLI (rich) + JSON rapor üretimi
│
├── web/                        # Web arayüzü katmanı
│   ├── server.py               # FastAPI backend (19 endpoint)
│   └── index.html              # Tek sayfa uygulama (Bootstrap 5 + Material Icons + vanilla JS)
│
├── tests/                      # Pytest test altyapısı
│   ├── test_vue_scanner.py     # 25 test
│   ├── test_stability_scorer.py # 20 test
│   └── test_locator_extractor.py # 7 test
│
├── main.py                     # CLI giriş noktası
├── config.yaml                 # Proje yapılandırması
├── setup.bat                   # Tek seferlik kurulum (venv + bağımlılıklar)
├── run_web.bat                 # Web sunucusu başlatma
├── run.bat                     # CLI komut çalıştırma
└── requirements.txt            # Tüm bağımlılıklar (CLI + Web + Slack)
```

---

## Kurulum

### Hızlı Başlangıç (Windows)

```bat
setup.bat       ← venv oluşturur + tüm bağımlılıkları yükler
run_web.bat     ← http://localhost:8000
```

### Manuel Kurulum

```bash
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # Linux/macOS

pip install -r requirements.txt
```

> `requirements.txt` CLI + Web UI + Slack entegrasyonu için gereken tüm paketleri içerir.
> Ayrıca `requirements-web.txt` yüklemeye gerek yoktur.

---

## Yapılandırma

`config.yaml` dosyasını düzenleyin:

```yaml
vue_project:
  path: "C:/projelerim/my-vue-app"        # Vue kaynak dosyaları (güncel)
  old_path: "C:/projelerim/my-vue-app-v1" # Eski snapshot (vue-diff için, opsiyonel)

robot_project:
  path: "C:/projelerim/robot-tests"  # .robot / .resource dosyaları

analysis:
  stability_threshold: 50    # Bu skorun altı "riskli" sayılır
  critical_threshold: 30     # Bu skorun altı "kritik" sayılır

healing:
  backup_before_patch: true  # Patch öncesi .bak dosyası oluştur

reporting:
  output_dir: "reports"      # JSON raporların kaydedileceği klasör
  save_json: true
```

---

## CLI Kullanımı

### 1. Durum Kontrolü
```bash
python main.py status
```
Yapılandırmanın doğru okunup okunmadığını kontrol eder.

### 2. data-test Denetimi
```bash
python main.py data-test-audit
python main.py data-test-audit --min-coverage 90
```
Vue bileşenlerinde `data-test` / `data-testid` eksik olan interaktif elementleri raporlar.

### 3. Vue Stabilite Analizi
```bash
python main.py vue-only
```
Vue elementlerinin locator stabilitesini skorlar, en kırılgan 10 elementi gösterir.

### 4. Çapraz Analiz
```bash
python main.py analyze
python main.py analyze --json    # JSON rapor da kaydet
```
Robot Framework locator'larını Vue elementi ile eşleştirir, kırık/riskli olanları tespit eder.

### 5. Heal (Otomatik Düzeltme)
```bash
python main.py heal                    # Sadece öneri üret
python main.py heal --patch            # Patch dosyaları hazırla
python main.py heal --patch --apply    # Patch'leri doğrudan uygula
python main.py heal --patch --apply --dry-run   # Simülasyon (dosya değiştirmez)
python main.py heal --patch --apply --only-high # Sadece yüksek güvenli patch'ler
```

---

## Web Arayüzü

Tüm ekibin kullanımı için web sunucusunu başlatın:

```bash
run_web.bat
```

Tarayıcıda açın: `http://localhost:8000`

Aynı ağdaki diğer bilgisayarlar: `http://[bilgisayar-ip]:8000`

### Web UI Özellikleri

Arayüz Sigortam.net marka kimliği esas alınarak tasarlanmıştır:

- **Tasarım:** Bootstrap 5 + Inter font; Sigortam.net brand renkleri — mavi `#0071BC`, turuncu `#FF6600`; dark sidebar `#1c232f`
- **Favicon & Marka:** Shield SVG ikonu (turuncu gradient zemin, beyaz stroke) + "LocatorSync" logosu
- **Sidebar ikonlar:** Feather tarzı inline SVG'ler; turuncu renk, aktif durum glow efekti
- **Sidebar:** Navigasyon, proje listesi (ekle / düzenle / **her satırda sil butonu**) ve son raporlar
- **Data-Test Audit:** Kapsama raporu, eksik elementler ve önerilen data-test adları
- **Vue Analizi:** Stabilite dağılımı, en kırılgan 10 element
- **Çapraz Analiz:** Kırık ve riskli locator tabloları, kırılma/risk oranları
- **Heal:** Düzeltme önerileri, Dry-Run ve canlı patch uygulama (onay diyaloğu ile)
- **Vue Fark Analizi:** Eski/yeni Vue karşılaştırması, etkilenen Robot locator'ları
- **data-test Ekle:** Vue dosyalarına otomatik `data-test` ekler — Önizle → satır satır seçim (checkbox) → Dry-Run → Seçilileri Uygula akışı
- **ID Ekle:** Vue'da `data-test`/`:data-test` olan ama `id` olmayan elementlere aynı değerde `id` ekler. Dynamic binding (`:data-test="getAttributeName(...)"`) desteklenir — bu durumda `:id="..."` yazılır. Robot'taki `css=[data-test='X']` locatorları otomatik `id=X` ile değiştirilir. **Önemli:** Bu sekme yalnızca projenin güncel (yeni) Vue yolunu tarar ve günceller; eski Vue yolu yalnızca "Vue Fark Analizi" için kullanılır (sekmede bilgi notu olarak da gösterilir).
- **Eşik alanları:** Proje formunda RF locator hiyerarşisini gösteren "Skor Tablosu" açılır; UYARI/KRİTİK etiketleri ile eşik açıklamaları
- **Tarama Önceliği:** Proje ayarlarında klasör öncelik sırası belirlenir (örn. `po, app, test, object`). Robot dosyaları bu sırayla taranır; CSS ve XPath locator'ları sonuç tablolarında otomatik olarak öne alınır ve mor renk ile vurgulanır.
- **Klasör Etiketleri:** Analiz sonuçlarında her locator satırında dosyanın ait olduğu klasör türü (PO / App / Test / Obj) badge olarak gösterilir.
- **Sticky Tablo Başlıkları:** Uzun sonuç listelerinde aşağı kaydırıldığında sütun başlıkları (Dosya:Satır, Locator, Skor vb.) ekranın üstünde sabit kalır.
- **Slack Entegrasyonu:** Her analiz sonucu ekranında "Slack'e Gönder" butonu; proje bazlı Incoming Webhook URL ile Block Kit formatında rapor gönderilir
- **Eş Zamanlı Koruma:** Aynı anda yalnızca bir analiz çalışır (`asyncio.Lock`); ikinci istek "Analiz devam ediyor" uyarısı alır
- **Hata Bildirimi:** API hataları hem inline hem Vue tarzı bottom-center fade toast ile QA geliştiricisine gösterilir
- **Git Yazma Engeli:** `heal/apply` ve `patch-vue/apply`, Git'ten çekilen kaynaklara yazma girişimini engeller

### Git / Yerel Kaynak Seçimi

Her proje kaynağı için **Yerel** veya **Git** arasında toggle ile seçim yapılır:

| Kaynak | Yerel | Git |
|--------|-------|-----|
| Vue (güncel) | Klasör yolu | URL + branch + alt dizin |
| Eski Vue (diff) | Klasör yolu | URL + branch/tag/commit |
| Robot | Klasör yolu | URL + branch + alt dizin |

- Git kaynakları analiz başlamadan önce geçici dizine `--depth 1` ile klonlanır, analiz bitince silinir.
- Commit hash, branch ve tag formatlarının tümü desteklenir.
- Yerel ve Git kaynakları aynı projede karıştırılabilir (örn. Vue yerel, Robot git).

---

## Stabilite Skoru Tablosu

Robot Framework locator arama sırası: **ID → ClassName → Name → TagName → LinkText → CssSelector → XPath → DOM**

| Skor | Locator Türü | Açıklama |
|------|-------------|----------|
| 95 | `data-test` / `data-testid` | ★ Bu projede öncelikli — en stabil |
| 85 | `ID` | RF'de ilk aranır, statikse stabil |
| 70 | `Name` | Form elementleri için iyi |
| 65 | `LinkText` | Metin değişirse bozulur |
| 50 | `CssSelector` | Orta stabil — UI lib sınıflarından kaçın |
| 35 | `ClassName` | Riskli — UI değişince bozulur |
| 25 | `TagName` | Çok riskli — semantik anlam yok |
| 10 | `XPath` (index) / `DOM` | Kritik — DOM sırası değişince kırılır |

**Eşikler:**
- `>= 80` → YUKSEK (yeşil)
- `50–79` → ORTA (sarı)
- `30–49` → DUSUK (turuncu)
- `< 30` → KRITIK (kırmızı)

---

## data-test Otomatik Ekleme

`VuePatcher` modülü, `DataTestAuditor`'ın tespit ettiği eksik `data-test` attribute'larını doğrudan Vue dosyalarına yazar.

### Değer Belirleme Önceliği

1. **Mevcut `id` attribute** — element'in zaten bir `id="submit-btn"` değeri varsa `data-test="submit-btn"` olarak kullanılır
2. **Bağlam tabanlı türetme** — inner text, name, aria-label'dan oluşturulur
3. **Fallback** — tag adı kullanılır

### Kullanım (Web UI)

1. Sol menüden **"data-test Ekle"** sekmesine geç
2. **"Önizle"** butonuna tıkla — hangi dosyalarda neyin değişeceğini gösteren iki tablo açılır:
   - **Robot-Driven**: Kırılgan locator'ı olan elementler → Vue'ya `id` eklenir
   - **Audit-Driven**: Robot'ta hiç referans olmayan elementler → `data-test` eklenir
3. Satır satır **checkbox** ile uygulamak istediğin elementleri seç (varsayılan: tümü seçili)
   - "Tümünü Seç" ile tüm satırları toplu seç/kaldır
   - Tablo başlığındaki checkbox ile sadece o tablonun tümünü seç
4. **"Dry-Run"** ile seçili satırları simüle et (dosya değişmez)
5. **"Seçilileri Uygula"** ile onay diyaloğu sonrası uygula

> **Not:** Git kaynağından çekilen Vue projelerine yazma engellenir. Uygulama için Vue kaynağı "Yerel" olmalıdır.

### Teknik Detaylar

- Multi-line tag desteği: `<input\n  type="text"\n/>` gibi yapılar desteklenir
- Tırnak içindeki `>` karakterleri atlanır (attribute parser ile)
- Zaten `data-test` olan elementler atlanır
- Yüksek satır numarasından aşağı doğru işlenir (satır kayması önlenir)

---

## Heal Güven Seviyeleri

| Güven | Açıklama | Otomatik Patch? |
|-------|----------|-----------------|
| **high** | Vue elementinde `data-test` veya `id` mevcut | Evet |
| **medium** | `name` veya `aria-label` mevcut | Evet |
| **low** | Eşleşme bulunamadı, öneri tahmini | Hayır (manuel inceleme) |

---

## API Endpoint'leri

```
GET    /api/projects                    Proje listesi
POST   /api/projects                    Yeni proje ekle
PUT    /api/projects/{name}             Proje güncelle
DELETE /api/projects/{name}             Proje sil
GET    /api/projects/{name}/validate    Yol doğrulama
POST   /api/projects/{name}/audit       data-test denetimi
POST   /api/projects/{name}/vue-only    Vue stabilite analizi
POST   /api/projects/{name}/analyze     Çapraz analiz
POST   /api/projects/{name}/heal        Heal önerileri
POST   /api/projects/{name}/heal/apply       Patch uygula
POST   /api/projects/{name}/diff             Vue eski/yeni snapshot karşılaştırması
POST   /api/projects/{name}/patch-vue        data-test eksiklerini önizle (dosya değişmez)
POST   /api/projects/{name}/patch-vue/apply  data-test attribute'larını Vue dosyalarına yaz
GET    /api/reports                          Rapor listesi
GET    /api/reports/{filename}               Rapor indir
```

---

## Testleri Çalıştırma

```bash
venv\Scripts\python.exe -m pytest tests/ -v
```

**54 test — tamamı geçiyor:**
- `tests/test_vue_scanner.py` — 25 test (data-test parsing, lstrip bug fix)
- `tests/test_stability_scorer.py` — 20 test
- `tests/test_locator_extractor.py` — 7 entegrasyon testi

---

## Mimari Kararlar

Bu proje, `automation_robot` projesindeki page-object katmanlı mimariden ilham alınarak tasarlanmıştır:

| Katman | Sorumluluk |
|--------|-----------|
| `configs/` | Yapılandırma okuma (YAML veya dict) |
| `models/` | Veri yapıları — sadece dataclass, iş mantığı yok |
| `enums/` | Tip güvenliği için sabit değerler |
| `core/` | İş mantığı — domain'e göre alt klasörlere ayrılmış |
| `services/` | Yatay kesim — raporlama, I/O |
| `web/` | Sunum katmanı — FastAPI + HTML |

**Temel prensipler:**
- Her modül tek bir sorumluluğa sahip
- `models/` ve `enums/` hiçbir şeye import bağımlılığı yok
- `core/` sadece `models/` ve `enums/` import eder, `services/` import etmez
- `web/server.py` tüm katmanları birleştirir, YAML gerektirmez (`AppConfig.from_dict()`)
