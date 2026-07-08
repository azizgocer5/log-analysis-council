"""Academic knowledge base references for control systems, aerodynamics, and structural vibrations."""

from typing import Dict

PID_TUNING_THEORY = """
### AKADEMİK KONTROL TEORİSİ & PID YÖNLENDİRMELERİ
1. **Kaskad Kontrol Yapısı**:
   PX4 Autopilot, dış çevrimde konum/tutum (attitude) kontrolü ve iç çevrimde açısal hız (rate) kontrolü içeren kaskad bir yapı kullanır.
   - Dış çevrim: $u(t) = K_p e(t)$ (Sadece P kontrolcü)
   - İç çevrim: $u_{rate}(t) = K_{p\\_rate} e_{rate}(t) + K_{i\\_rate} \\\\int e_{rate}(\\\\tau) d\\\\tau + K_{d\\_rate} \\\\frac{d e_{rate}(t)}{dt} + K_{ff} r_{setpoint}$

2. **Ziegler-Nichols & Cohen-Coon Metotları (Referans)**:
   - *Ziegler-Nichols Adım Yanıtı*:
     - $K_p = 1.2 / (R \\\\cdot L)$
     - $T_i = 2.0 \\\\cdot L$
     - $T_d = 0.5 \\\\cdot L$
     (Burada $L$ ölü zaman (dead time), $R$ ise eğim/maksimum hızdır.)
   - *Aşırı Aşım (Overshoot) ve Faz Payı (Phase Margin)*:
     - Klasik PX4 tuning'de hedef faz payı $45^\\\\circ$ ile $60^\\\\circ$ arasındadır.
     - Aşırı sönümlü (overdamped) sistemlerde $MC\\\\_*_D$ katsayısı gürültü yükseltmeyecek şekilde artırılır. Ancak yüksek D katsayısı motorlarda yüksek frekanslı ısınmaya sebep olur.

3. **Kontrol Döngüsü Gecikmesi (Control Loop Latency)**:
   - Toplam sistem gecikmesi $\\\\tau_{total} = \\\\tau_{sensor} + \\\\tau_{filter} + \\\\tau_{compute} + \\\\tau_{actuator}$.
   - Gecikme $> 20$ ms ise, $K_p$ kazanç sınırları düşürülmelidir, aksi takdirde gecikme kaynaklı limit çevrim (limit cycle) osilasyonları başlar.
"""

VTOL_AERODYNAMICS = """
### VTOL AERODİNAMİK VE GEÇİŞ (TRANSITION) TEORİSİ
1. **İtme-Ağırlık Oranı (Thrust-to-Weight Ratio - TWR)**:
   - VTOL araçlarında hover için gereken minimum TWR $1.5$ olmalıdır. Güvenli operasyonlar ve rüzgar kompanzasyonu için $1.8$ - $2.2$ arası önerilir:
     $TWR = \\\\frac{T_{total}}{m \\\\cdot g}$
   - Motor itki dağılımı (Rotor output spread) CoG (Ağırlık Merkezi) sapması ile doğrudan ilişkilidir:
     $x_{CoG} = \\\\frac{\\\\sum_{i} T_i \\\\cdot x_i}{\\\\sum_{i} T_i}$

2. **Geçiş Evresi Kaldırma/İtme Paylaşımı (Transition Lift-Thrust Split)**:
   - Geçiş sırasında kanat kaldırma kuvveti ($L = \\\\frac{1}{2} \\\\rho V^2 S C_L$) arttıkça, lift motorlarının yükü kademeli olarak azalır.
   - Stall hızı ($V_{stall} = \\\\sqrt{\\\\frac{2 W}{\\\\rho S C_{L\\_max}}}$) geçişin tamamlanması için kritik alt sınırdır. Pusher motoru aracı $V_{stall} \\\\times 1.2$ hızına ulaştırmadan lift motorları kapatılmamalıdır (Transition Timeout).
"""

STRUCTURAL_VIBRATION = """
### YAPISAL VİBRASYON & ISO STANDARTLARI REFERANSLARI
1. **Vibrasyon Seviyesi ve İvme Analizi (Vibration Severity)**:
   - ISO 2631 standardı insan ve hassas elektronikler için titreşim sınırlarını belirler. UAV otopilotları (Cube Orange+ vb.) için:
     - İyi sönümlenmiş gövde: $\\\\text{RMS}_{accel} < 5$ m/s²
     - Riskli seviye (clipping/veri kaybı başlangıcı): $\\\\text{RMS}_{accel} > 15$ m/s²
     - Kritik donanımsal arıza riski: $\\\\text{RMS}_{accel} > 25$ m/s²

2. **Dinamik Filtreleme ve Notch (Yarık) Filtre Tasarımı**:
   - Pervane/Rotor dönme frekansı: $f_{prop} = \\\\frac{\\\\text{RPM}}{60} \\\\cdot \\\\text{Bıçak Sayısı}$
   - IMU notch filtreleri ($IMU\\\\_GYRO\\\\_*\\\\_FREQ$) rotor dönme frekansındaki tepe gürültüleri sönümlemek üzere dar bantlı tasarlanmalıdır:
     $H(s) = \\\\frac{s^2 + \\\\omega_0^2}{s^2 + \\\\Delta \\\\omega \\\\cdot s + \\\\omega_0^2}$
     (Burada $\\\\omega_0$ rezonans frekansı, $\\\\Delta \\\\omega$ ise filtre bant genişliğidir.)
"""

ARDUPILOT_VTOL_TUNING = """
### ArduPilot QuadPlane VTOL Tuning Süreci (Detaylı Referans)
Kaynak: https://ardupilot.org/plane/docs/quadplane-vtol-tuning-process.html

**DOĞRU TUNİNG SIRASI (Bu sırayı asla atlama):**

1. **Ön Hazırlık — Thrust Linearization:**
   - Voltaj düşmesi kompanzasyonu: Q_M_BAT_VOLT_MAX (4.2V × hücre sayısı), Q_M_BAT_VOLT_MIN (3.3V × hücre sayısı)
   - Motor endpoint ayarı: Her motorun min/max PWM değerlerini doğru ayarla
   - Thrust expo: Lineer olmayan itki eğrisini düzeltmek için MOT_THST_EXPO ayarla

2. **Vibrasyon Filtreleme (PID'den ÖNCE):**
   - FFT analizi ile dominant frekansları tespit et
   - INS_HNTCH_ENABLE, INS_HNTCH_FREQ, INS_HNTCH_BW ile harmonik notch filtre ayarla
   - PX4 eşdeğerleri: IMU_GYRO_NF0_FRQ, IMU_GYRO_NF0_BW
   - Ağır araçlarda (>15kg) yapısal rezonans genelde 40-80 Hz, motor frekansı 80-120 Hz

3. **Rate Controller (İç Döngü):**
   - ArduPilot: ATC_RAT_RLL_P/I/D, ATC_RAT_PIT_P/I/D
   - PX4: MC_ROLLRATE_P/I/D, MC_PITCHRATE_P/I/D
   - Ağır VTOL baseline: P=0.12-0.18, I=0.15-0.20, D=0.002-0.004

4. **Attitude Controller (Dış Döngü):**
   - ArduPilot: ATC_ANG_RLL_P, ATC_ANG_PIT_P
   - PX4: MC_ROLL_P, MC_PITCH_P
   - Rate döngüsü stabil olduktan sonra ayarla

**KRİTİK UYARILAR:**
- Motor spread > 0.05 → PID tuning'den ÖNCE CoG düzelt
- D kazancı motor ısınmasına sebep olabilir → minimum tut
- QuickTune (Q_OPTIONS bit 12) otomatik başlangıç tune sağlar
"""

ACADEMIC_REFERENCES_LIST = """
### AKADEMİK VE TEKNİK LİTERATÜR REFERANSLARI
1. **IEEE Control Systems Technology**: "L1 Adaptive Control for VTOL UAVs during Transition Phases" (Adaptive control methods, tracking optimization).
2. **PX4 Autopilot User Guide (docs.px4.io)**: "VTOL Control Architecture and Multicopter to Fixed-Wing Transition Tuning Guide".
3. **Journal of Guidance, Control, and Dynamics**: "System Identification and Robust Control of Heavy Lift Multirotor UAVs under Actuator Constraints".
4. **ISO 2631-1**: "Mechanical vibration and shock -- Evaluation of human exposure to whole-body vibration -- Part 1: General requirements" (Sönümleme jeli ve mekanik izolasyon referansı).
5. **ArduPilot QuadPlane VTOL Tuning Process**: https://ardupilot.org/plane/docs/quadplane-vtol-tuning-process.html
6. **ArduPilot Notch Filter Configuration**: https://ardupilot.org/copter/docs/common-imu-notch-filtering.html
7. **PX4 Vibration Isolation Guide**: https://docs.px4.io/main/en/assembly/vibration_isolation.html
"""

def get_academic_context(persona_id: str) -> str:
    """Returns academic context tailored for a specific persona."""
    context = ""
    
    if persona_id == "pid_tuning_expert":
        context = PID_TUNING_THEORY + "\n" + ARDUPILOT_VTOL_TUNING + "\n" + ACADEMIC_REFERENCES_LIST
    elif persona_id == "hardware_diagnostics_expert":
        context = STRUCTURAL_VIBRATION + "\n" + ARDUPILOT_VTOL_TUNING + "\n" + ACADEMIC_REFERENCES_LIST
    elif persona_id == "sensor_safety_expert":
        context = (
            "### EKF KABUL VE REFERANS KRİTERLERİ\n"
            "1. **EKF2 Innovation Test Ratios**: EKF, sensör ölçümleriyle tahmin edilen durumlar arasındaki farkları "
            "normalize ederek izler. Test ratio < 0.5 olmalıdır. Gelişmiş Kalman Filtrelerinde tutarlılık "
            "$\\chi^2$ (Chi-square) dağılım testi ile belirlenir.\n"
            + "\n" + ACADEMIC_REFERENCES_LIST
        )
    elif persona_id == "chairman":
        context = PID_TUNING_THEORY + "\n" + VTOL_AERODYNAMICS + "\n" + STRUCTURAL_VIBRATION + "\n" + ARDUPILOT_VTOL_TUNING + "\n" + ACADEMIC_REFERENCES_LIST
    else:
        # Fallback for any unknown persona
        context = ARDUPILOT_VTOL_TUNING + "\n" + ACADEMIC_REFERENCES_LIST
        
    return context
