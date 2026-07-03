# PX4 VTOL Geçiş (Transition) ve Havada Kalma Hata Teşhis Kılavuzu

VTOL (Dikey Kalkış ve İniş) uçaklarının en kritik aşaması Multikopter (MC) modundan Sabit Kanat (FW) moduna geçiş (Forward Transition) ve geri dönüş (Backward Transition / Quadchute) aşamalarıdır.

## 1. Quadchute Failsafe (Multikopter Acil Geri Dönüşü)
Quadchute, otopilotun Sabit Kanat modunda giderken kritik bir hata tespit edip uçağın düşmesini engellemek için dikey kaldırma motorlarını acilen çalıştırarak Multikopter moduna fallback yapmasıdır.

### A. Düşük Hava Hızı / Stall Durumu
- **Belirti:** Loglarda geçiş esnasında veya sonrasında `quadchute triggered: low airspeed` mesajı. Airspeed sensor verisinde ani düşüş veya dalgalanma.
- **Mekanik Teşhis:** 
  - **Tıkalı Pitot Tüpü (Clogged Airspeed Sensor):** Pitot tüpüne böcek, toz girmesi veya su yoğuşması nedeniyle basınç okunamaması.
  - **Yetersiz İtme Gücü:** İtici motorun (pusher) veya pervanesinin ters takılması, ESC sınırlandırmaları veya batarya çökmesi nedeniyle uçağın stall hızının (`FW_AIRSPD_MIN`) üzerine çıkamaması.
- **Çözüm:** Pitot tüpü temizliği, üfleyerek kalibrasyon testi, itici motor pervane yönü ve çekiş gücü kontrolü.

### B. Aşırı Pitch/Roll Açı Sapmaları (Attitude Failure)
- **Belirti:** Geçiş sırasında `quadchute triggered: pitch angle limit exceeded` veya `roll angle limit exceeded`.
- **Mekanik Teşhis:** 
  - **Aşırı Trim Açısı İhtiyacı:** Sabit kanat kanatçıklarının (ailerons/ruddervator) mekanik olarak nötr pozisyonda durmaması. Uçak geçişe başladığında motor torkundan veya kaldırma kuvvetinden dolayı ani burun dikme/düşürme eğilimi gösterir. Otopilot servolarla bunu dengeleyemeyince güvenliği korumak için quadchute tetikler.
  - **Hatalı Ağırlık Merkezi (CoG):** Aşırı burun ağır veya kuyruk ağır durumlar kontrol limitlerini aşar.
- **Çözüm:** Kontrol yüzeylerinin mekanik olarak sıfırlanması, linkage boşluklarının alınması, CoG kontrolü.

## 2. İtici (Pusher) Motor Hataları ve Geçiş Zaman Aşımı
- **Belirti:** Geçiş (transition) aşamasının çok uzun sürmesi (transition timeout) ve otopilotun geçişi yarıda keserek hata vermesi.
- **Mekanik Teşhis:**
  - **İtici Motor Verimsizliği:** Pervane montaj hatası (pervanenin arka yüzünün öne bakacak şekilde ters takılması çekişi %30-40 düşürür).
  - **Mekanik Eğrilik:** İtici motor şaftının uçuş eksenine tam paralel olmaması, uçağın geçiş sırasında sürekli sapma (yaw/pitch) yapmasına neden olur.
- **Çözüm:** Pervane yönü kontrolü (yazılar uçuş yönüne bakmalıdır), motor yatağı montaj açısının kontrolü.

## 3. İlgili PX4 Parametreleri ve Limitler
- **`VT_ARSP_TRANS` (Varsayılan: VTOL'e göre değişir, VTOL assembly: 22.0 m/s):** Multikopter motorlarının kapatılması için uçağın ulaşması gereken minimum hava hızı. Bu hıza ulaşılmadan geçiş tamamlanmaz.
- **`VT_TRANS_MIN_TM` (Varsayılan: 2.0s):** Geçiş aşamasının sürmesi gereken minimum saniye.
- **`VT_FW_MIN_ALT` (Varsayılan: 20.0m):** Quadchute failsafe'inin aktif olması için gereken minimum irtifa. Bu irtifanın altında quadchute koruması devreye girmeyebilir.
- **`VT_FW_QC_P` (Varsayılan: 75°):** Quadchute tetiklenmesi için izin verilen maksimum pitch sapması.
- **`VT_FW_QC_R` (Varsayılan: 60°):** Quadchute tetiklenmesi için izin verilen maksimum roll sapması.
- **`TRIM_PITCH` (Varsayılan: 0.14 rad):** Sabit kanat uçuşunda düz uçağın burnunu kaldırmak için kullanılan aerodinamik trim açısı.
