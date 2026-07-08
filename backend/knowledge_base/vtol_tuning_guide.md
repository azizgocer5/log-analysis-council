# VTOL Tuning Guide — ArduPilot & PX4 Combined Reference

## Tuning Sırası (Kritik — Bu Sırayı Asla Atlama)

### Adım 1: Mekanik Hazırlık
- Motor kollarının hizasını kontrol et (twisted arm → kalıcı motor spread)
- Pervane balansını kontrol et (titreşim kaynağı #1)
- Ağırlık Merkezi (CoG) kontrolü — pil ve yük yerleşimi
- Pixhawk/Cube montaj sönümlemesini kontrol et (dampening pads)
- Motor spread < 0.05 olmalı, > 0.05 ise mekanik düzeltme yap

### Adım 2: Thrust Curve Linearization
- **Voltaj Düşmesi Kompanzasyonu:**
  - ArduPilot: Q_M_BAT_VOLT_MAX = 4.2V × hücre sayısı, Q_M_BAT_VOLT_MIN = 3.3V × hücre sayısı
  - PX4: Otomatik (battery_status topic'inden)
- **Thrust Expo:**
  - ArduPilot: MOT_THST_EXPO (genelde 0.5-0.75 arası)
  - Lineer olmayan itki eğrisi → PID tuning yanlış sonuç verir
- **Motor Endpoint:**
  - ESC kalibrasyonu, min/max PWM ayarları
  - Tüm motorların aynı RPM aralığında dönmesi gerekir

### Adım 3: Vibrasyon Filtreleme (PID'den ÖNCE)
- **FFT Analizi:** Uçuş logundaki sensor_combined/sensor_accel verilerinden FFT yaparak dominant frekansları belirle
- **Harmonik Notch Filtre:**
  - ArduPilot: INS_HNTCH_ENABLE=1, INS_HNTCH_FREQ, INS_HNTCH_BW
  - PX4: IMU_GYRO_NF0_FRQ, IMU_GYRO_NF0_BW (1. filtre), IMU_GYRO_NF1_FRQ, IMU_GYRO_NF1_BW (2. filtre)
- **Tipik Frekanslar (Ağır VTOL 20-30 kg):**
  - Motor/pervane kaynaklı: 80-120 Hz
  - Yapısal rezonans (karbon kol): 40-80 Hz
  - Gövde esnekliği: 20-50 Hz

### Adım 4: Rate Controller (İç Döngü) Tuning
- **Parametre Eşdeğerleri:**

| Özellik | ArduPilot | PX4 |
|---------|-----------|-----|
| Roll Rate P | ATC_RAT_RLL_P | MC_ROLLRATE_P |
| Roll Rate I | ATC_RAT_RLL_I | MC_ROLLRATE_I |
| Roll Rate D | ATC_RAT_RLL_D | MC_ROLLRATE_D |
| Pitch Rate P | ATC_RAT_PIT_P | MC_PITCHRATE_P |
| Pitch Rate I | ATC_RAT_PIT_I | MC_PITCHRATE_I |
| Pitch Rate D | ATC_RAT_PIT_D | MC_PITCHRATE_D |

- **Ağır VTOL Baseline (23.5 kg):**
  - P: 0.12-0.18 (> 0.25 agresif)
  - I: 0.15-0.20 (rüzgar/CoG kompanzasyonu için yeterli)
  - D: 0.002-0.004 (> 0.006 motor ısınması riski)

### Adım 5: Attitude Controller (Dış Döngü) Tuning
- **Parametre Eşdeğerleri:**

| Özellik | ArduPilot | PX4 |
|---------|-----------|-----|
| Roll P | ATC_ANG_RLL_P | MC_ROLL_P |
| Pitch P | ATC_ANG_PIT_P | MC_PITCH_P |
| Yaw P | ATC_ANG_YAW_P | MC_YAW_P |

- **Baseline:** MC_ROLL_P = MC_PITCH_P = 5.5-6.5
- Rate döngüsü stabil olmadan dış döngüye dokunma!

## Ağır VTOL'lerde Bilinen Sorunlar

### 1. Voltaj Düşmesi (Voltage Sag)
- Pusher motor devreye girdiğinde batarya voltajı aniden düşer
- Bu, lift motorlarının thrust curve'ünü bozar
- Çözüm: Voltaj kompanzasyonu aktif et, ayrı batarya kullan

### 2. Motor Spread (Thrust Asymmetry)
- Spread > 0.05 → CoG sapması veya motor kolu bükülmesi
- PID ile kompanse etmeye çalışma, mekanik olarak düzelt
- Çapraz motorlar arası fark → yaw axis'te sürekli düzeltme

### 3. Yapısal Rezonans
- Karbon kol esnekliği + yüksek P/D kazancı = limit cycle osilasyonu
- Belirtisi: Motor ısınması, buzz/hum sesi
- Çözüm: Notch filtre + D kazancını azalt

### 4. IMU Gürültüsü
- Sönümleme jeli eskimesi → IMU gürültüsü artar
- EKF innovation ratio'ları yükselir
- Çözüm: Dampening aparatını yenile, montaj kontrolü yap

## Referans Kaynaklar
- [ArduPilot QuadPlane VTOL Tuning](https://ardupilot.org/plane/docs/quadplane-vtol-tuning-process.html)
- [ArduPilot Notch Filtering](https://ardupilot.org/copter/docs/common-imu-notch-filtering.html)
- [PX4 MC PID Tuning Guide](https://docs.px4.io/main/en/config_mc/pid_tuning_guide_multicopter.html)
- [PX4 Vibration Isolation](https://docs.px4.io/main/en/assembly/vibration_isolation.html)
- [ArduPilot Motor Thrust Scaling](https://ardupilot.org/plane/docs/motor-thrust-scaling.html)
