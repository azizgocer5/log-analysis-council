# PX4 Vibrasyon ve IMU Spektrum Arıza Teşhis Kılavuzu

Vibrasyon, otopilot sensörlerinin sıhhati ve uçuş kontrol kararlılığı için en kritik fiziksel faktördür. IMU verilerindeki gürültü ve yüksek vibrasyonlar doğrudan mekanik/donanımsal sorunlara işaret eder.

## 1. Vibrasyon Seviyeleri ve Sınır Değerler
Otopilot loglarındaki akselerometre (accel) vibrasyon seviyeleri şu şekilde değerlendirilir:
- **RMS Akselerometre Vibrasyonu < 5 m/s²:** Çok İyi. Gövde rijit, pervaneler dengeli.
- **RMS 5 - 15 m/s²:** Kabul edilebilir. Uçuş stabil kalabilir ancak aşınma veya ufak gevşeklikler olabilir.
- **RMS > 15 m/s²:** Kötü/Tehlikeli. Sensör gürültüsü nedeniyle EKF konum/irtifa tahminlerinde sapma (velocity innovation peaks) ve ani irtifa kayıpları yaşanabilir.
- **IMU Clipping (Kırpılma):** IMU ivmeölçerinin ölçüm sınırının (örn. ±16g) aşılmasıdır. Logdaki `clip_counter` sıfır olmalıdır. Herhangi bir clipping (> 0), sensörün doyum noktasına ulaştığını ve acil mekanik müdahale gerektiğini gösterir.

## 2. Frekans Spektrumu (FFT) ve Mekanik Hata İlişkileri
Groskop veya akselerometre verilerinden elde edilen FFT (Hızlı Fourier Dönüşümü) spektrumundaki baskın zirveler (peaks) doğrudan donanımsal kaynakları gösterir:

### A. Pervane Dengesizliği (Propeller Imbalance)
- **Belirti:** Motorların çalışma RPM'ine karşılık gelen yüksek frekanslarda (genellikle 80 Hz ile 150 Hz arasında) çok net, keskin dominant frekans zirveleri.
- **Mekanik Teşhis:** Pervanelerde mikro çatlaklar, kir birikmesi, balans bozukluğu veya adaptör gevşekliği.
- **Çözüm:** Pervanelerin balans aletinde dengelenmesi, çatlak kontrolü yapılması veya motor şaftının bükülme kontrolü.

### B. Gövde ve Karbon Kol Esnekliği (Structural Resonance)
- **Belirti:** Daha düşük frekanslarda (20 Hz ile 60 Hz arasında) geniş tabanlı veya yüksek genlikli spektrum zirveleri.
- **Mekanik Teşhis:** Karbon kolların gövdeye bağlantı vidalarında gevşeme, motor yatağı vidalarında gevşeklik, iniş takımlarında rezonans veya gövdede aşırı esnek karbon malzeme kullanımı.
- **Çözüm:** Tüm mekanik vida ve somunların Loctite ile sıkılması, karbon kolların rijitliğinin artırılması.

### C. Otopilot Montaj Hataları (FC Dampening Failure)
- **Belirti:** 10 Hz altındaki düşük frekanslı salınımlar ve telemetry verilerinde kontrol edilemeyen yavaş yalpalamalar (attitude RMSE > 2.0°).
- **Mekanik Teşhis:** Cube/Pixhawk otopilotunun gövdeye montajında kullanılan sönümleme jellerinin (dampening pads) sertleşmesi, eskimesi veya otopilota bağlı kabloların çok gergin olması (kablolar mekanik titreşimi doğrudan FC'ye aktarır).
- **Çözüm:** Sönümleme pad'lerinin yenilenmesi, kablo ağlarının gevşetilerek serbest hareket marjı verilmesi.

## 3. İlgili PX4 Parametreleri ve Yazılımsal Çözümler
Mekanik iyileştirmelerin yanında yazılımsal filtrelerin doğru ayarlanması vibrasyonu bastırabilir:
- **`IMU_GYRO_CUTOFF` (Varsayılan: 80 Hz, VTOL assembly: 50 Hz):** Jiroskop ham verisi için alçak geçiren filtre (low-pass filter) eşiği. Vibrasyon yüksekse 30-40 Hz değerlerine çekilerek gürültü filtrelenebilir.
- **`IMU_ACCEL_CUTOFF` (Varsayılan: 30 Hz):** İvmeölçer alçak geçiren filtre eşiği.
- **Notch Filtreleri (`IMU_GYRO_NF0_FRQ`, `IMU_GYRO_NF0_BW`):** FFT analizinde tespit edilen spesifik bir motor gürültü frekansını (örn. 92 Hz) hedef alarak dar bir bantta gürültüyü yok eder. Mekanik sorunun çözülemediği durumlarda yazılımsal cankurtarandır.
