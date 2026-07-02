# UAV Log Analysis Council (İHA Log Analiz Konseyi)

[![VTOL Log Analysis](header.jpg)](header.jpg)

UAV Log Analysis Council; gelişim aşamasındaki VTOL (Dikey Kalkış ve İniş) ve multikopter İHA uçuş loglarını (`.ulg` formatında) parse eden, gelişmiş istatistiksel analizler (FFT titreşim analizi, EKF innovation takibi, PID tracking RMSE) gerçekleştiren ve uzman bir LLM konseyi (5 uzman persona ve 1 baş mühendis sentezi) aracılığıyla iyileştirme reçeteleri ve PX4 parametre değişiklik tabloları sunan gelişmiş bir yerel web uygulamasıdır.

Bu proje, orijinal [karpathy/llm-council](https://github.com/karpathy/llm-council) reposundan çatallanarak (fork) tamamen havacılık ve İHA telemetri analizine odaklanacak şekilde özelleştirilmiştir.

---

## 🛠️ Nasıl Çalışır? (3 Aşamalı Konsey Akışı)

Kullanıcı bir veya birden fazla log seçip analizi başlattığında şu adımlar sırasıyla gerçekleştirilir:

1. **Log Ayrıştırma ve İstatistik Üretimi:** Seçilen `.ulg` dosyaları arka planda hızlıca parse edilir. Ham IMU verileri üzerinden FFT analizi yapılarak titreşim pikleri bulunur, EKF innovation ratio'ları hesaplanır, Roll/Pitch/Yaw RMSE setpoint takip hataları çıkarılır ve pil anomalileri saptanır.
2. **Aşama 1: Uzman Görüşleri (First Opinions):** 5 farklı uzman persona (Aerodinamik, Vibrasyon, EKF, Güvenlik, Test Pilotu), kendi uzmanlık alanlarına göre log verilerini detaylıca inceler ve bağımsız reçetelerini yazar.
3. **Aşama 2: Çapraz Değerlendirme (Cross-Evaluation):** Uzmanlar, birbirlerinin reçetelerini ve parametre değişiklik önerilerini güvenlik ve uçuş dinamiği açısından eleştirir (örn. Kaptan Güvenlik, Aerodinamik hocanın önerdiği agresif PID kazançlarını sorgular).
4. **Aşama 3: Nihai Sentez Raporu (Chairman Synthesis):** Konsey başkanı **Baş Mühendis**, tüm uzman görüşlerini ve eleştirilerini sentezleyerek çelişkileri çözer. Sonuçta önceliklendirilmiş nihai bir reçete listesi, **PX4 Parametre Değişiklik Tablosu** ve bir sonraki uçuş için **Test Uçuşu Planı** çıkarır.

---

## 🔬 Uzman Personalar ve Görevleri

*   **🎓 Prof. Aerodinamik (PID Uzmanı):** Roll, Pitch ve Yaw RMSE değerlerini ve setpoint takip kalitesini inceler. Açısal hız takip hatalarına göre PID katsayılarını optimize eder.
*   **🔧 Saha Mühendisi Kemal (Mekanik & Titreşim):** Ham IMU verilerinden FFT analizi yapar, motor/pervane kaynaklı rezonansları bulur ve Notch Filtre (`IMU_GYRO_NF_FREQ`) frekansları önerir.
*   **📡 Dr. Sensör (EKF & Sensör Füzyonu):** GPS, Pusula ve Barometre innovation test oranlarını inceleyerek manyetik girişimleri, sensör gürültülerini ve bias kaymalarını tespit eder.
*   **🛡️ Kaptan Güvenlik (Emniyet & Failsafe):** Logdaki hata mesajlarını, pil kritik voltaj alarmlarını ve failsafe mod geçişlerini analiz ederek riskleri raporlar.
*   **✈️ Test Pilotu Ece (Uçuş Performansı):** Hover kalitesini ve stabiliteyi test pilotu gözüyle değerlendirerek bir sonraki test uçuşu için adım adım pratik bir test planı sunar.

---

## 🌟 Öne Çıkan Özellikler

*   **Çoklu Log Karşılaştırma:** Birden fazla log seçildiğinde sistem uçuşları yan yana karşılaştırır. PID parametrelerindeki değişimi ve RMSE iyileşmelerini otomatik olarak tablo halinde sunar.
*   **Canlı İlerleme Takibi (Progress Bar):** Log ayrıştırmadan nihai rapor sentezine kadar tüm adımları ve LLM çağrılarını görsel olarak takip edebilirsiniz.
*   **Mod Değiştirici:**
    *   **Tam Analiz:** Logların derinlemesine 3 aşamalı konsey incelemesini yapar.
    *   **Soru Sor:** Seçilen loglar bağlamında konseye serbest sorular sormanızı sağlar (örn: *"12. dakikadaki irtifa kaybının sebebi ne olabilir?"*).
*   **Yüksek Performanslı Cache:** Loglar bir kez parse edildikten sonra `data/log_cache` dizininde saklanır. Böylece aynı logu tekrar analiz ederken parsing aşaması anında tamamlanır.
*   **İptal Desteği (Abort Controller):** Uzman analizlerini veya LLM sorgularını istediğiniz an güvenle durdurabilirsiniz.

---

## 🔌 Kurulum ve Çalıştırma

### 1. Gereksinimler
*   Python 3.10+
*   Node.js (v18+)
*   [uv](https://docs.astral.sh/uv/) (Hızlı Python paket yönetimi için önerilir)

### 2. Bağımlılıkların Yüklenmesi

**Backend:**
```bash
uv sync
```

**Frontend:**
```bash
cd frontend
npm install
cd ..
```

### 3. API Anahtarlarının Yapılandırılması

Proje kök dizininde bir `.env` dosyası oluşturun ve API anahtarınızı tanımlayın (Varsayılan olarak Gemini API kullanılır, alternatif olarak OpenRouter API kullanılabilir):

```env
GEMINI_API_KEY=AIzaSy...
# VEYA
OPENROUTER_API_KEY=sk-or-v1-...
```

Log dosyalarınızın okunacağı klasör yolunu da `.env` içinde belirtebilirsiniz (varsayılan olarak `../../data/log` kullanılır):
```env
LOG_DIR=../../data/log
```

### 4. Uygulamayı Başlatma

**Seçenek 1: Otomatik Başlatma Betiği**
```bash
./start.sh
```

**Seçenek 2: Manuel Başlatma**

1. Terminalde Backend'i ayağa kaldırın:
   ```bash
   uv run python -m backend.main
   ```

2. Terminalde Frontend'i başlatın:
   ```bash
   cd frontend
   npm run dev
   ```

Ardından tarayıcınızda [http://localhost:5173](http://localhost:5173) adresine giderek arayüze erişebilirsiniz.

---

## 💻 Kullanılan Teknolojiler

*   **Backend:** FastAPI (Python), `pyulog` (PX4 ULog parsing), `numpy` & `pandas` (Veri analizi ve FFT), Google Gemini API / OpenRouter (Sentez ve Konsey modelleri).
*   **Frontend:** React + Vite, CSS Custom Properties (Koyu slate / mavi kontrol odası teması), Markdown parser (`react-markdown`).
*   **Paket Yönetimi:** Python için `uv`, JavaScript için `npm`.
