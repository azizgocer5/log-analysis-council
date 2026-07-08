# Benzer VTOL Araç Referansları ve PID Baseline Değerleri

## 20-30 kg Sınıfı Standard VTOL Quadplane Referansları

### Referans Araç Profili
- **Tip:** Standard VTOL Quadplane (4 lift rotor + 1 pusher)
- **Ağırlık:** 20-30 kg
- **Otopilot:** Cube Orange / Cube Orange+ / Pixhawk 6X
- **Firmware:** PX4 v1.14+ veya ArduPilot 4.4+

### Baseline PID Değerleri (Ağır VTOL, 23.5 kg referans)

#### Rate Controller (İç Döngü)
| Parametre | Başlangıç | Optimize Edilmiş | Agresif (Max) | Not |
|-----------|-----------|-----------------|---------------|-----|
| MC_ROLLRATE_P | 0.12 | 0.15-0.18 | 0.25 | >0.25 yapısal rezonans riski |
| MC_ROLLRATE_I | 0.10 | 0.15-0.20 | 0.35 | Rüzgar/CoG kompanzasyonu |
| MC_ROLLRATE_D | 0.001 | 0.002-0.003 | 0.006 | >0.004 motor ısınması |
| MC_PITCHRATE_P | 0.12 | 0.15-0.18 | 0.25 | Roll ile simetrik (±20%) |
| MC_PITCHRATE_I | 0.10 | 0.15-0.20 | 0.35 | |
| MC_PITCHRATE_D | 0.001 | 0.002-0.003 | 0.006 | |
| MC_YAWRATE_P | 0.15 | 0.18-0.25 | 0.40 | Genelde roll/pitch'ten yüksek |
| MC_YAWRATE_I | 0.05 | 0.10 | 0.25 | |

#### Attitude Controller (Dış Döngü)
| Parametre | Başlangıç | Optimize Edilmiş | Max |
|-----------|-----------|-----------------|-----|
| MC_ROLL_P | 4.5 | 5.5-6.5 | 9.0 |
| MC_PITCH_P | 4.5 | 5.5-6.5 | 9.0 |
| MC_YAW_P | 2.0 | 2.5 | 4.5 |

#### Notch Filter Ayarları
| Parametre | Varsayılan | Önerilen | Not |
|-----------|-----------|----------|-----|
| IMU_GYRO_NF0_FRQ | 0 (devre dışı) | Motor RPM frekansı (80-120 Hz) | FFT ile belirle |
| IMU_GYRO_NF0_BW | 20 | 15-25 | Dar bant, fazla genişletme |
| IMU_GYRO_NF1_FRQ | 0 (devre dışı) | Yapısal rezonans (40-80 Hz) | Varsa etkinleştir |
| IMU_GYRO_NF1_BW | 20 | 10-20 | |
| IMU_GYRO_CUTOFF | 30 | 40-80 | Düşük gecikme vs gürültü dengesi |

### Performans Hedefleri (Başarı Kriterleri)

#### Hover Stabilite
| Metrik | İyi | Kabul Edilebilir | Kötü |
|--------|-----|-------------------|------|
| Roll RMSE | < 1.0° | 1.0° - 2.2° | > 2.2° |
| Pitch RMSE | < 1.0° | 1.0° - 2.2° | > 2.2° |
| Yaw RMSE | < 1.8° | 1.8° - 3.5° | > 3.5° |
| Roll Rate RMSE | < 6°/s | 6° - 18°/s | > 18°/s |
| Motor Spread | < 0.05 | 0.05 - 0.15 | > 0.15 |
| Alt Stddev | < 0.4m | 0.4 - 1.0m | > 1.0m |

#### Vibrasyon
| Metrik | İyi | Kabul Edilebilir | Kötü |
|--------|-----|-------------------|------|
| Accel RMS | < 5 m/s² | 5 - 15 m/s² | > 15 m/s² |
| Accel Peak | < 30 m/s² | 30 - 60 m/s² | > 60 m/s² |
| IMU Clipping | 0 | 1 - 100 | > 100 |

### Bilinen Başarılı Konfigürasyonlar

#### Konfigürasyon A: 24 kg Quadplane, PX4 v1.14
- MC_ROLLRATE_P = 0.16, I = 0.18, D = 0.003
- MC_PITCHRATE_P = 0.16, I = 0.18, D = 0.003
- MC_ROLL_P = 6.0, MC_PITCH_P = 6.0
- IMU_GYRO_NF0_FRQ = 95 (motor kaynaklı), NF0_BW = 20
- Sonuç: Roll RMSE = 0.8°, Pitch RMSE = 0.7°, Motor Spread = 0.03

#### Konfigürasyon B: 22 kg Quadplane, ArduPilot 4.5
- ATC_RAT_RLL_P = 0.14, I = 0.16, D = 0.002
- ATC_RAT_PIT_P = 0.14, I = 0.16, D = 0.002
- INS_HNTCH_FREQ = 88, INS_HNTCH_BW = 22
- Sonuç: Roll RMSE ≈ 0.9°, stabil hover, düşük motor sıcaklığı

#### Konfigürasyon C: 28 kg Hexaplane, PX4 v1.15
- MC_ROLLRATE_P = 0.12, I = 0.15, D = 0.002
- MC_PITCHRATE_P = 0.12, I = 0.15, D = 0.002
- İki notch filtre: NF0 = 75 Hz (yapısal), NF1 = 110 Hz (motor)
- Not: Ağır araç → daha düşük P kazancı ile kararlı

### Yaygın Hatalar ve Çözümleri

| Hata | Belirti | Çözüm |
|------|---------|-------|
| PID tuning before notch filter | Yüksek D → motor ısınması | Önce FFT + notch, sonra PID |
| Çok yüksek I kazancı | Yavaş osilasyon (0.5-2 Hz) | I'yi azalt, FF ekle |
| CoG sapması varken PID tune | Asimetrik motor wear | Önce mekanik dengeleme |
| Gyro cutoff çok düşük | Yüksek gecikme, sluggish response | Cutoff'u artır (40-80) |
| Notch BW çok geniş | Faz kaybı, kontrol gecikmesi | BW'yi daralt (15-25) |

## Forum ve Topluluk Referansları
- ArduPilot Discuss: https://discuss.ardupilot.org/c/arduplane-quadplane/
- PX4 Discuss: https://discuss.px4.io/c/flight-controller/vtol/
- PX4 GitHub Issues: https://github.com/PX4/PX4-Autopilot/issues (VTOL label)
