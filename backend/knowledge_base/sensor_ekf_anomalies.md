# PX4 Sensör ve EKF (Kalman Filtresi) Arıza Teşhis Kılavuzu

EKF2 (Extended Kalman Filter), otopilotun uçuş durumunu (konum, hız, irtifa, attitude) tahmin eden ana algoritmadır. Sensörlerdeki donanımsal veya çevresel hatalar EKF sağlığını doğrudan bozar.

## 1. Pusula (Magnetometre) Hataları ve Manyetik Girişim
Pusula, uçağın yönelimini (heading) belirlemede kritiktir. 

### A. Yüksek Güç Kablosu Yakınlığı (Magnetic Interference)
- **Belirti:** Motor gazı (throttle / current) arttığında pusula tutarsızlığı (`compass inconsistent` mesajları) ve yaw inovasyon oranında (`mag_yaw_innovation`) ani yükselme.
- **Mekanik Teşhis:** GPS/Pusula modülünün altından veya çok yakınından yüksek akım taşıyan batarya/ESC güç kabloları geçiyordur. Akım geçtikçe oluşan elektromanyetik alan pusulayı yanıltır.
- **Çözüm:** Pusula modülünün fiziksel olarak yükseltilmesi (GPS direği kullanılması), güç kablolarının birbirine dolanarak (twisted pair) manyetik alanın sönümlenmesi veya pusulanın güç dağıtım kartından en az 10-15 cm uzağa taşınması.

### B. Gövde İçi Metal Parçalar / Yapısal Demir
- **Belirti:** Kalibrasyon yapılmasına rağmen pusula tutarsızlığı veya yaw estimation stabilitesinin bozulması.
- **Mekanik Teşhis:** Gövdede pusulaya yakın konumlandırılmış demir vidalar, çelik linkage elemanları veya mıknatıslı kabin kilitleri manyetik sapmaya yol açıyordur.
- **Çözüm:** Pusula yakınındaki çelik vidaların titanyum, alüminyum veya plastik vidalarla değiştirilmesi.

## 2. EKF Innovation Test Ratios (İnovasyon Test Oranları)
EKF, sensör ölçümleri ile kendi tahmini arasındaki farkları inovasyon oranları ile izler:
- **Innovation Ratio < 0.5:** Çok İyi. Sensörler tutarlı.
- **Ratio 0.5 - 1.0:** Sınır değer. Dikkat edilmeli.
- **Ratio > 1.0:** Hata durumu. EKF o sensörden gelen veriyi "reddetmeye" başlar. Eğer bu süre uzarsa EKF sensörü tamamen devre dışı bırakır ve failsafe durumuna geçer.
  - **`gps_hpos` / `gps_hvel` inovasyonunun artması:** GPS sinyal kalitesinde düşüş, çoklu yansıma (multipath) veya karıştırma (jamming).
  - **`mag_3d` / `mag_yaw` inovasyonunun artması:** Manyetik sapma veya pusula montaj açısının gövdeye tam paralel olmaması.

## 3. Barometrik İrtifa Sapması ve Statik Port Aerodinamiği
- **Belirti:** Hover sırasında dikey konum sapması (altitude hold stddev > 0.8m) veya yüksek hızlı forward flight esnasında barometre irtifayı gerçekte olduğundan çok farklı (örneğin 10-15 metre daha yüksek veya alçak) gösteriyor.
- **Mekanik Teşhis (Fuselage static pressure buildup):** Otopilot gövdesinin iç tasarımı aerodinamik hava akışına maruz kalıyordur. Uçak hızlandıkça gövde içinde statik basınç birikir (veya vakum oluşur), bu da barometreyi yanıltır.
- **Çözüm:** Statik basınç portlarının (havalandırma deliklerinin) aerodinamik olarak türbülanssız ve rüzgara dik maruz kalan bölgelerde konumlandırılması veya gövdenin sızdırmazlığının artırılarak FC'nin doğrudan rüzgar akımına maruz kalmasının engellenmesi.

## 4. İlgili PX4 Parametreleri
- **`EKF2_MAG_TYPE` (Varsayılan: 0):** Manyetik füzyon tipi. 0 = 3D magnetometre füzyonu. 5 = Sadece yaw füzyonu (manyetik alanın çok bozuk olduğu büyük VTOL'lerde kullanılır).
- **`EKF2_GPS_CHECK`:** GPS sinyal kalitesi doğrulama seviyesi.
- **`EKF2_HGT_REF`:** EKF için ana irtifa referansı (0 = Barometre, 1 = GPS, 2 = Range finder).
