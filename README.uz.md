<p align="center"><img src="custom_components/domo/brand/logo@2x.png" alt="DOMO" height="64"></p>

[English](README.md) | [Русский](README.ru.md) | **Oʻzbekcha**

# Home Assistant uchun DOMO

[DOMO](https://domo.uz) ilovasidagi (Hududgaz) barcha shaxsiy hisob raqamlari boʻyicha balans va isteʼmol: tabiiy gaz, elektr energiyasi, suv, chiqindi olib ketish, «Mening uyim» va boshqa xizmatlar.

Bu norasmiy integratsiya. U DOMO yoki Hududgaz bilan bogʻliq emas.

## Kirish qanday ishlaydi

DOMO’da parol yoʻq. Ilovada roʻyxatdan oʻtgan telefon raqamini kiritasiz, DOMO SMS-kod yuboradi. Kod bir marta kiritiladi, keyin integratsiya kirishni oʻzi saqlab turadi:

- Kirish tokeni 7 kun amal qiladi. Integratsiya uni muddati tugashidan bir kun oldin yangilaydi.
- Yangilash tokeni 365 kun amal qiladi. Har bir yangilash uni uzaytiradi, shuning uchun Home Assistant ishlab tursa, sessiya tugamaydi.
- Agar DOMO sessiyani baribir yakunlasa, Home Assistant qayta avtorizatsiya haqida xabar koʻrsatadi. Uni tasdiqlasangiz, yangi SMS-kod keladi.

Ilovadagi faol seanslar roʻyxatida Home Assistant **Home Assistant** nomi bilan koʻrinadi. Telefoningizdagi kirish saqlanib qoladi.

## Oʻrnatish

### HACS

1. HACS → ⋮ → **Custom repositories** → `https://github.com/dilshodm/ha-domo` manzilini qoʻshing, toifa **Integration**.
2. **DOMO**ni oʻrnating va Home Assistant’ni qayta ishga tushiring.

### Qoʻlda

`custom_components/domo` papkasini `config/custom_components` ichiga nusxalang va Home Assistant’ni qayta ishga tushiring.

### Sozlash

**Sozlamalar → Qurilmalar va xizmatlar → Integratsiya qoʻshish → DOMO**. Telefon raqamini, soʻng SMS-kodni kiriting.

## Obyektlar

Har bir hisob raqami xizmat nomi va hisob raqami bilan nomlangan qurilmaga aylanadi, masalan «Газ 1007090145». Qurilmaning model maydonida uy nomi yoki manzili koʻrsatiladi.

| Sensor | Hisoblar | Izoh |
|---|---|---|
| Balans | hammasi | UZS, DOMO koʻrsatganidek (musbat = ortiqcha toʻlov) |
| Hisoblagich koʻrsatkichi | gaz, elektr | m³ / kVt·soat, `total_increasing`, «Energiya» paneli uchun mos |
| Koʻrsatkich sanasi | hisoblagichli | oxirgi koʻrsatkich vaqti |
| Oylik isteʼmol | gaz, elektr | m³ / kVt·soat |
| Oy uchun hisoblangan | DOMO tahlil qiladigan hisoblar | UZS; `previous_month` atributi |
| Oxirgi kun isteʼmoli / hisoblangan | gaz, elektr | DOMO kunlik statistikasidagi oxirgi kun; `date` atributi |
| Yangilangan | hammasi | diagnostika: DOMO hisobni oxirgi marta qachon sinxronlagani |

Kirishning oʻzi ham qurilma sifatida koʻrinadi (**DOMO +998…**), unda **Maʼlumotlarni yangilash** tugmasi bor. U DOMO’dan barcha hisoblarni yetkazib beruvchilar bilan qayta sinxronlashni soʻraydi (ilovadagi pastga tortib yangilash kabi) va keyingi soʻrovni kutmasdan natijani darhol oladi. Muvaffaqiyatli yangilashdan keyin tugmani bir daqiqadan soʻng yana bosish mumkin.

### Yangi hisoblar

DOMO ilovasida xizmat yoki uy qoʻshsangiz, yangi qurilma va sensorlar keyingi soʻrovda Home Assistant’da paydo boʻladi. Ularni darhol koʻrish uchun **Maʼlumotlarni yangilash** tugmasini bosing. Hisob DOMO’dan oʻchirilsa, uning sensorlari mavjud boʻlmaydi, qurilmani esa uning sahifasida oʻchirish mumkin.

## Parametrlar

**Sozlamalar → Qurilmalar va xizmatlar → DOMO → Sozlash**:

- **Soʻrov oraligʻi**: 1 dan 24 soatgacha, standart qiymat 3. DOMO isteʼmolni taxminan kuniga bir marta yangilaydi.
- **Til**: Русский, Oʻzbekcha yoki English. DOMO javoblari tili va qurilma nomlarini belgilaydi («Газ / Gaz / Gas 1007090145»). U dastlabki sozlashda ham soʻraladi, standart qiymat Home Assistant tili. Sensor nomlari odatdagidek Home Assistant tiliga mos boʻladi.

## Maxfiylik

Telefon raqami va DOMO tokenlari faqat Home Assistant konfiguratsiya yozuvida saqlanadi. Ular faqat `domo-gw.uz` bilan ishlash uchun ishlatiladi va boshqa joyga yuborilmaydi.
