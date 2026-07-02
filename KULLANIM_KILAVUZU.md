# UAV Log Analysis Council — Kullanım Kılavuzu

Bu sistem, developmental VTOL (Dikey Kalkış ve İniş) İHA uçuş loglarını (.ulg formatında) parse etmek, istatistiksel analizler (FFT titreşim analizi, EKF innovation takibi, PID tracking RMSE) gerçekleştirmek ve uzman bir LLM konseyi (5 uzman persona ve 1 başkan sentezi) aracılığıyla iyileştirme reçeteleri sunmak üzere tasarlanmıştır.

---

## 1. Arayüz Bileşenleri ve Genel Düzen

Arayüz sadeleştirilmiş, gözü yormayan profesyonel bir kontrol odası temasına (koyu slate/mavi tonları) sahiptir.

1. **Sol Panel (Log Seçimi ve Kontroller)**:
   - **Log Ağacı**: Loglar tarih ve oturum bazlı (örneğin `2026-06-24` veya `sess007`) gruplanmıştır. Her logun boyutu ve cache durumu yanlarında belirtilir.
   - **Tümünü Seç / Seçimi Temizle**: Oturum bazlı veya genel hızlı seçim yapmanızı sağlar.
   - **Mod Değiştirici**:
     - **🔬 Tam Analiz**: Logların derinlemesine incelenmesini ve nihai bir sentez raporu üretilmesini sağlar.
     - **💬 Soru Sor**: Seçilen loglar bağlamında konseye serbest sorular sormanızı sağlar (ör: *"Titreşim seviyeleri kabul edilebilir sınırda mı?"*).
   - **Filtre / Odak Girişi**: Analizi başlatmadan önce konseyin odaklanmasını istediğiniz konuyu yazabilirsiniz (ör: *"PID kazançlarını düşürmeye odaklan"*).
   - **Başlat / Durdur Butonu**: Analizi tetikler veya devam eden analizi anında keser.

2. **Sağ Panel (Analiz Sonuçları ve Aşamalar)**:
   - **Progress Bar**: Log Parsing → Uzman Analizleri → Çapraz Değerlendirme → Sentez adımlarının ilerlemesini canlı olarak gösterir.
   - **Sekmeler**:
     - **Nihai Rapor**: Başkan modelin (Baş Mühendis) tüm konsey bulgularını sentezlediği, PX4 parametre değişiklik tablosu ve sonraki test uçuş planını içeren ana bölümdür.
     - **Uzman Analizleri**: 5 uzmanın kendi uzmanlık alanlarındaki detaylı raporları ve reçeteleri (Ör: Kemal'in FFT grafik açıklamaları, Aerodinamik hocanın RMSE hesapları).
     - **Çapraz Değerlendirme**: Uzmanların birbirlerinin reçetelerini güvenlik ve uygulanabilirlik açısından değerlendirdiği tartışma alanı.

---

## 2. Adım Adım Analiz Akışı

### Adım 1: Log Seçimi
Sol log ağacından analiz etmek istediğiniz uçuş loglarını seçin. 
> 💡 **PID Tuning için Karşılaştırmalı Analiz**: Birden fazla log seçtiğinizde (örneğin ayar yapmadan önceki uçuş ile yapıldıktan sonraki uçuş), sistem otomatik olarak logları karşılaştırır ve PID parametrelerindeki değişimi ve RMSE iyileşmelerini tablo halinde size sunar.

### Adım 2: Odak Belirleme (Opsiyonel)
Alt kısımdaki metin alanına konseyin dikkat etmesini istediğiniz özel bir durum varsa yazın (örn: *"18:33:01 logunda yaşanan attitude failure sebebini araştırın"*).

### Adım 3: Analizi Başlatma
**🚀 Council Analizi Başlat** butonuna tıklayın. 
Sistem logları parse ederken sol üstte canlı ilerleme çubuğu görünür. Eğer işlem uzun sürerse veya yanlış logları seçtiğinizi fark ederseniz **🛑 Analizi Durdur** butonuna tıklayarak işlemi istediğiniz an iptal edebilirsiniz.

---

## 3. Uzman Personalar ve Görevleri

- **Prof. Aerodinamik (PID Uzmanı)**: Roll, Pitch ve Yaw RMSE değerlerini inceler. Setpoint takibindeki gecikme veya aşırı salınımlara göre PID katsayılarını optimize eder.
- **Saha Mühendisi Kemal (Mekanik & Titreşim)**: Ham IMU verilerinden FFT analizi yapar, motor/propeller kaynaklı rezonansları bulur ve Notch Filter frekansları önerir.
- **Dr. Sensör (EKF & Sensör Füzyonu)**: GPS, Pusula ve Barometre innovation test ratio'larını inceleyerek sensörlerdeki sapmaları ve bias kaymalarını tespit eder.
- **Kaptan Güvenlik (Emniyet & Failsafe)**: Logtaki hata mesajlarını, pil kritik voltaj alarmlarını ve failsafe mod geçişlerini analiz ederek risk raporu sunar.
- **Test Pilotu Ece (Uçuş Performansı)**: Hover kalitesi ve genel stabiliteyi test pilotu gözüyle değerlendirerek bir sonraki test uçuşu için adım adım test planı sunar.

---

## 4. Çıktıların Yorumlanması

- **PX4 Parametre Değişiklik Tablosu**: Nihai Raporun altında bulunur. Önerilen parametre değişikliklerinin mevcut değerlerini, önerilen yeni değerlerini, risk durumunu ve gerekçesini net bir şekilde görebilirsiniz.
- **FFT Frekansları**: Titreşim raporunda listelenen peak frekanslar (örn: `84.5Hz`), PX4 üzerinde `IMU_GYRO_NF_FREQ` filtre parametresi olarak atanabilir.
- **Hata Mesajları Kronolojisi**: EKF veya Güvenlik sekmesinde logta geçen tüm sistem mesajları zaman etiketleriyle birlikte listelenir.
