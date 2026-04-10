# Logika biznesowa ZETOM CRM (v.0.3)

**Cel dokumentu:** Uzgodnienie architektury obsługi zgłoszeń, systemów powiadomień oraz podziału odpowiedzialności (Model Ról).

---

## 1. Cykl życia zgłoszenia (Lifecycle)

Proces kontroli w systemie jest podzielony na dwa niezależne poziomy. Pozwala to na wyraźne rozróżnienie globalnej „aktualności” klienta od bieżącego etapu operacyjnego.

### 1.1. Statusy globalne (Aktualność)
Określają, czy klient jest aktualnie procesowany:
* **Active (Aktywne):** Zgłoszenie jest w trakcie obsługi (na dowolnym z czterech cykli).
* **Archive (Archiwalne):** Praca została zakończona lub przymusowo wstrzymana. Dane są „zamrożone” na potrzeby historii i analityki.

### 1.2. Cykle operacyjne i ich statusy
Każdy etap (cykl) to osobny obszar roboczy z dokumentami. W ramach bieżącego cyklu zgłoszenie przechodzi przez następujące stany:
* **New (Nowe):** Etap właśnie się rozpoczął, nie podjęto jeszcze żadnych działań.
* **In Progress (W toku):** Specjalista rozpoczął edycję danych lub wprowadził nowe informacje.
* **Waiting (Oczekiwanie):** System zarejestrował wysłanie wiadomości e-mail do klienta i oczekuje na informację zwrotną.
* **Done (Gotowe):** Prace nad bieżącym cyklem/dokumentem zostały w pełni zakończone.

---

## 2. Cykl NULL: Bufor sanitarny i ochrona danych

**NULL** to pierwotny bufer dla wszystkich zapytań przychodzących ze strony internetowej.

**Cel w systemie:**
1. **Filtrowanie spamu:** Specjalista odfiltrowuje spam i „puste” zapytania, zanim trafią one do głównego działu operacyjnego (Oferta).
2. **Kontrola duplikatów:** System w tle sprawdza numer telefonu, e-mail oraz NIP. W momencie otwarcia zgłoszenia pracownik widzi już werdykt: „Czyste” lub „Znaleziono duplikat” (wraz z linkiem do oryginału).

---

## 3. Model ról: Podział odpowiedzialności

### 3.1. Hierarchia dostępu
System opiera się na ścisłej strukturze podległości:
**Dyrektor (Admin) > Kierownik działu (Department Head) > Specjalista (Specialist)**

### 3.2. Role specjalne
Role te znajdują się poza główną hierarchią i służą do konkretnych zadań:
* **Użytkownik niestandardowy (Custom):** Rola z dynamicznymi uprawnieniami (konfigurowana pod zadanie). Nie może mieć wyższych uprawnień niż Admin, ale może mieć mu równe (np. dla zastępcy).
* **Audytor:** Rola techniczna dla programisty. **Bez prawa do edycji** jakichkolwiek danych. Tylko wgląd w logi i incydenty w celu kontroli poprawności systemu.

### 3.3. Tabela uprawnień
| Rola | Znaczenie biznesowe | Poziom dostępu |
| :--- | :--- | :--- |
| **Dyrektor (Admin)** | Właściciel systemu | Maksymalny dostęp. Zarządzanie zgłoszeniami, logami i kontami użytkowników. |
| **Użytkownik Custom** | Osoba zaufana | Elastyczna rola dla zadań zarządczych, z uprawnieniami „powyżej średniej”. |
| **Kierownik działu** | Dyspozytor / Kontroler | Widzi zgłoszenia swojego działu. Przypisuje specjalistów. Kontroluje terminy. |
| **Specjalista** | Wykonawca | Widzi tylko te zgłoszenia, do których został przypisany przez kierownika lub admina. |
| **Audytor** | Kontrola techniczna | Tryb „Tylko do odczytu” dla technicznego audytu systemu. |

---

## 4. System powiadomień i kontroli (Punkty do uzgodnienia)

W celu skonfigurowania efektywnej komunikacji musimy zdefiniować wyzwalacze powiadomień:

1. **Pierwotne przypisanie:**
   - Zgłoszenie trafia do NULL → Powiadomienie dla Kierownika działu w celu przydzielenia.
   - Kierownik przypisuje Specjalistę → Powiadomienie dla Specjalisty.

2. **Kontrola zmian:**
   - Czy Pan lub Kierownik działu potrzebujecie powiadomień o każdej zmianie pośredniej (status `In Progress`)?
   - Czy wystarczy powiadomienie o faktycznym zakończeniu kluczowych etapów (status `Done` na końcu cyklu)?

3. **Informowanie o sytuacjach krytycznych:**
   - Czy wymagane jest natychmiastowe powiadomienie dla kierownictwa (Dyrektor lub Użytkownik Custom), jeśli zgłoszenie zostanie przeniesione do statusu **Archive**?

---

### Podsumowanie do zatwierdzenia:
1. Czy zgadza się Pan na rolę „Cyklu NULL” jako filtra dla nowych zgłoszeń?
2. Czy odpowiada Panu obecność roli niestandardowej (Custom) dla elastycznego nadawania uprawnień (np. dla zastępcy)?
3. W jakich przypadkach chce Pan osobiście otrzymywać powiadomienia o ruchu zgłoszeń (Punkt 4)?
4. Czy zgadza się Pan na podział na Statusy Globalne (zgłoszenie) i Statusy Operacyjne (wewnątrz cyklu)?
5. Czy akceptuje Pan diagram cyklu życia (dołączony do wiadomości)?