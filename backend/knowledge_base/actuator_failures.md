# PX4 Aktüatör ve Mekanik Güç Dağılımı Hata Teşhis Kılavuzu

Uçuş loglarındaki aktüatör ve motor çıkış komutları, aracın aerodinamik ve mekanik dengesine dair çok güçlü veriler sağlar.

## 1. Motor Ortalama Çıkış Dengesizliği (Motor Output Spread)
Multikopter modunda veya hover sırasında tüm kaldırma motorlarının (`actuator_outputs` veya `actuator_motors` topic'leri) ortalama çıkışları karşılaştırılmalıdır. Dengeli bir VTOL/Multikopterde motor çıkışları birbirine çok yakındır (fark < %5).

### A. Ağırlık Merkezi (CoG - Center of Gravity) Kayması
- **Belirti:** Ön motorlar (Motor 0 ve 2) veya arka motorlar (Motor 1 ve 3) sürekli olarak diğer çifte göre daha yüksek PWM/gaz seviyesinde çalışıyor (örneğin ön motorlar 0.65 hover gazında, arka motorlar 0.40 gazında).
- **Mekanik Teşhis:** Aracın fiziki ağırlık merkezi, tasarım geometrisinin önünde veya arkasındadır. Bu durum ağır motorların ısınmasına, verimsizliğe ve stabilite sınırının aşılmasına yol açar.
- **Çözüm:** Pil yerleşiminin (batarya kızağının) veya faydalı yükün (faydali yuk / payload) fiziksel olarak CoG eksenine doğru kaydırılması.

### B. Bükülmüş/Eğri Motor Kolları (Twisted Motor Arm)
- **Belirti:** Çapraz çalışan motorlar (örneğin CW dönen Motor 1 ve 3) sürekli olarak CCW dönen Motor 0 ve 2'ye göre çok yüksek güç tüketiyor. Yaw takibi için sürekli yüksek yaw rate komutu üretiliyor.
- **Mekanik Teşhis:** Motor kollarından bir veya birkaçı eksenel olarak bükülmüştür. Motor şaftları tam olarak dikey (90 derece) durmadığı için istenmeyen yaw momenti üretir ve otopilot bunu dengelemek için çapraz motorlara yüklenir.
- **Çözüm:** Motor montaj plakalarının ve kollarının gövdeye tam paralelliğinin kumpas/açı ölçer yardımıyla kontrol edilmesi ve düzeltilmesi.

### C. ESC/Motor Aşınması veya Yapısal Güç Kaybı
- **Belirti:** Sadece tek bir motorun (örneğin sadece Motor 2) ortalama çıkış seviyesi, simetriğindeki motorlara kıyasla belirgin şekilde yüksek.
- **Mekanik Teşhis:** Rulman aşınması, sargı hasarı, ESC kalibrasyon bozukluğu veya pervanedeki yapısal deformasyon nedeniyle o motor verim kaybetmiştir. Otopilot irtifa/attitude korumak için o motora daha fazla PWM göndermek zorundadır.
- **Çözüm:** İlgili motorun boşta dönüş direncinin elle kontrol edilmesi, rulmanların yağlanması/değiştirilmesi, ESC kalibrasyonunun yenilenmesi veya pervanenin değiştirilmesi.

## 2. Kontrol Yüzeyleri, Mekanik Boşluklar (Slop/Slack) ve Servolar
VTOL'lerde kanat aileronları ve ruddervator gibi kontrol yüzeyleri aerodinamik kararlılığı sağlar.

### A. Servo Linkage Boşluğu (Mechanical Slop)
- **Belirti:** Sabit kanat (FW) uçuşunda veya geçiş (transition) anında yüksek Roll/Pitch RMSE sapması (> 2.5°), ancak motor angular rates (rate loop) RMSE sapmaları normal.
- **Mekanik Teşhis:** Servo kolundan kontrol yüzeyine giden metal rodların (pushrods) veya küresel mafsalların (ball links) yuvalarında aşırı boşluk vardır. Rüzgar yükü altında kontrol yüzeyleri titrer (flutter) veya otopilot komutlarına gecikmeli yanıt verir.
- **Çözüm:** Aşınmış linkage elemanlarının yenilenmesi, vida bağlantılarının sıkılaştırılması.

### B. Servo Sıkışması veya Aşırı Yük
- **Belirti:** Güç telemetry loglarındaki servo akımında (5V/BEC akımı) anlık yüksek akım sıçramaları ve eş zamanlı attitude kontrol kaybı.
- **Mekanik Teşhis:** Servo dişlilerinde kırılma, kontrol yüzeyi menteşelerinde aşırı sürtünme veya aerodinamik yük altında servonun stall olması.
- **Çözüm:** Servo dişlilerinin metal tiptekilerle değiştirilmesi, menteşelerin serbest hareket kabiliyetinin kontrol edilmesi.

## 3. İlgili PX4 Parametreleri
- **`MPC_THR_HOVER` (Varsayılan: 0.50):** Aracın hover yapması için gereken ortalama gaz seviyesi. Heavy VTOL'lerde (23.50 kg gibi) bu değerin doğru ayarlanması kalkıştaki ani sıçramaları veya çökmeleri önler. `actuator_motors` ortalamasına bakılarak güncellenmelidir.
- **`CA_ACT_EN` / `CA_AIRFRAME`:** Aktüatör matrisi ve gövde tipi tanımları.
