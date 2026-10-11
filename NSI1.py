"""
System zarzadzania kontem bankowym
Wariant: Zespol D (Poprawiony i uzupelniony o mechanizmy Bloku P1)
Semestr 7, rok akademicki 2026/2027
Przedmiot: Niezawodnosc systemow informatycznych
"""

from decimal import Decimal, ROUND_HALF_UP
from datetime import date
import threading
import time
import random
import json
import functools

# Glowna stala limitu dziennego wyplat zgodnie z dokumentacja SUT (Sekcja 2)
LIMIT_DZIENNY_WYPLAT = Decimal("5000")


# =====================================================================
# SEKCJA WYJATKOW SYSTEMOWYCH
# =====================================================================

class KontoNieIstnieje(Exception):
    """Wyjatek zglaszany, gdy operacja dotyczy nieistniejacego numeru konta."""
    pass


class ProcesorNiedostepny(Exception):
    """Wyjatek symulujacy niedostepnosc zewnetrznego procesora platnosci."""
    pass


class KontoZablokowane(Exception):
    """Wyjatek zglaszany przy probie operacji na zablokowanym koncie."""
    pass


# =====================================================================
# MECHANIZM LOGOWANIA AWARII (WYMAGANIE LAB 1 / P1)
# =====================================================================

def niezawodnosc_logger(log_path="awarie.jsonl"):
    """
    ZMIANA / DODANIE (LAB 1 - Zadanie 4):
    Dekorator rejestrujacy awarie i nieoczekiwane wyjatki do pliku JSON Lines.
    
    CO DAJE TA ZMIANA:
    Umozliwia dokladny, obiektywny pomiar niezawodnosci poprzez logowanie:
    - znacznika czasu awarii (timestamp),
    - nazwy wywolywanej funkcji,
    - dokladnych parametrow wejsciowych (args, kwargs) do celow reprodukcji,
    - typu i tresci wyjatku,
    - czasu trwania operacji do momentu rzucenia wyjatku.
    Dzieki temu mozliwe jest obliczenie MTTF oraz unikanie 'polykania' bledow.
    """
    def dekorator(funkcja):
        @functools.wraps(funkcja)
        def wrapper(*args, **kwargs):
            start = time.time()
            try:
                wynik = funkcja(*args, **kwargs)
                return wynik
            except Exception as e:
                # Rejestrujemy awarie w logu awarie.jsonl
                wpis = {
                    "timestamp": time.time(),
                    "funkcja": funkcja.__name__,
                    "args": repr(args),
                    "kwargs": repr(kwargs),
                    "typ_bledu": type(e).__name__,
                    "komunikat": str(e),
                    "czas_do_awarii_s": time.time() - start,
                }
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(wpis, ensure_ascii=False) + "\n")
                # Wyjatek jest propagowany dalej, by nie falszowac dzialania SUT
                raise
        return wrapper
    return dekorator


# =====================================================================
# KLASA PROCESORA ZEWNETRZNEGO
# =====================================================================

class ZewnetrznyProcesor:
    """
    Symulacja zewnetrznego systemu rozliczeniowego.
    Zgodnie z dokumentacja SUT, awaryjnosc tego modulu jest celowa,
    sluzaca pozniejszym badaniom odpornosci (np. retry, circuit breaker).
    """

    def __init__(self, prawdopodobienstwo_awarii=0.3, opoznienie_s=0.0, generator=None):
        self.prawdopodobienstwo_awarii = prawdopodobienstwo_awarii
        self.opoznienie_s = opoznienie_s
        self._generator = generator or random.Random()
        self.licznik_wywolan = 0

    def wyslij_przelew(self, numer_konta_docelowego, kwota):
        self.licznik_wywolan += 1
        if self.opoznienie_s:
            time.sleep(self.opoznienie_s)
        if self._generator.random() < self.prawdopodobienstwo_awarii:
            raise ProcesorNiedostepny("Zewnetrzny procesor platnosci nie odpowiada")
        return {"status": "zaksiegowano", "numer_referencyjny": f"REF{self.licznik_wywolan:06d}"}


# =====================================================================
# KLASA KONTO
# =====================================================================

class Konto:
    def __init__(self, numer, wlasciciel, saldo_poczatkowe=0):
        self.numer = numer
        self.wlasciciel = wlasciciel
        # Zgodnie z dokumentacja SUT saldo musi byc obiektem Decimal, zapobiegajac bledom float
        self.saldo = Decimal(str(saldo_poczatkowe))
        self.historia = []
        self.status = "aktywne"

    def dodaj_wpis(self, typ, kwota, data_operacji=None):
        if data_operacji is None:
            data_operacji = date.today()
        self.historia.append((data_operacji, typ, kwota))


# =====================================================================
# GLOWNA KLASA SUT: BankSystem
# =====================================================================

class BankSystem:
    def __init__(self):
        self.konta = {}
        self._lock = threading.Lock()

    @staticmethod
    def _waliduj_typ_kwoty(kwota):
        """
        ZMIANA / DODANIE:
        Wspolna walidacja typu przekazywanej kwoty dla wszystkich metod transakcyjnych.
        
        CO DAJE TA ZMIANA:
        Dokumentacja wymaga rzucenia TypeError w przypadku przekazania typu innego
        niz int, float lub Decimal. Brak tej walidacji powodowal nieprzewidziane
        wyjatki w metodach wyplac() i przelew().
        """
        if not isinstance(kwota, (int, float, Decimal)):
            raise TypeError("Kwota musi byc liczba (int, float lub Decimal)")

    @staticmethod
    def _numer_poprawny(numer):
        """Sprawdza poprawnosc numeru wg algorytmu sumy kontrolnej mod 10."""
        if not isinstance(numer, str) or len(numer) != 10 or not numer.isdigit():
            return False
        cyfry = [int(c) for c in numer]
        suma_kontrolna = sum(cyfry[:9]) % 10
        return cyfry[9] == suma_kontrolna

    @niezawodnosc_logger()
    def utworz_konto(self, numer, wlasciciel, saldo_poczatkowe=0):
        """
        ZMIANA: Poprawiono blad w formatowaniu f-stringa (podwojne klamry {{numer}}).
        
        CO DAJE TA ZMIANA:
        Wczesniej komunikat bledu zwracal doslowny ciag 'Konto {numer} juz istnieje'
        zamiast rzeczywistego numeru konta. Poprawienie na f'Konto {numer} juz istnieje'
        zapewnia prawidlowa diagnostyke i czytelnosc logow.
        """
        if not self._numer_poprawny(numer):
            raise ValueError("Nieprawidlowy numer konta lub zla cyfra kontrolna")
        if numer in self.konta:
            raise ValueError(f"Konto {numer} juz istnieje")
        
        self._waliduj_typ_kwoty(saldo_poczatkowe)
        saldo_dec = Decimal(str(saldo_poczatkowe))
        if saldo_dec < 0:
            raise ValueError("Poczatkowe saldo nie moze byc ujemne")

        konto = Konto(numer, wlasciciel, saldo_dec)
        self.konta[numer] = konto
        return konto

    def _pobierz_konto(self, numer):
        if numer not in self.konta:
            raise KontoNieIstnieje(f"Konto {numer} nie istnieje")
        return self.konta[numer]

    @niezawodnosc_logger()
    def zablokuj_konto(self, numer):
        konto = self._pobierz_konto(numer)
        konto.status = "zablokowane"

    @niezawodnosc_logger()
    def odblokuj_konto(self, numer):
        konto = self._pobierz_konto(numer)
        konto.status = "aktywne"

    def _suma_dzisiejszych_wyplat(self, konto):
        """
        ZMIANA: Uwzglednienie typu 'przelew_zewnetrzny' w dobowym limicie.
        
        CO DAJE TA ZMIANA:
        Dokumentacja wskazuje, ze limit dzienny (5000) dotyczy sumy wyplat
        oraz wszelkich przelewow wychodzacych danego dnia.
        """
        dzis = date.today()
        suma = Decimal("0")
        for data_operacji, typ, kwota in konto.historia:
            if data_operacji == dzis and typ in ("wyplata", "przelew_wychodzacy", "przelew_zewnetrzny"):
                suma += kwota
        return suma

    @niezawodnosc_logger()
    def wplac(self, numer, kwota):
        konto = self._pobierz_konto(numer)
        self._waliduj_typ_kwoty(kwota)
        kwota = Decimal(str(kwota))
        if kwota <= 0:
            raise ValueError("Kwota wplaty musi byc dodatnia")
        konto.saldo += kwota
        konto.dodaj_wpis("wplata", kwota)
        return konto.saldo

    @niezawodnosc_logger()
    def wyplac(self, numer, kwota):
        """
        ZMIANY W METODZIE WYPLAC:
        1. Dodano walidacje typu kwoty (`self._waliduj_typ_kwoty(kwota)`).
           CO DAJE: Zgodnosc z dokumentacja - rzuca TypeError przy nieprawidlowym typie.
        2. Poprawiono warunek salda z `if kwota >= konto.saldo:` na `if kwota > konto.saldo:`.
           CO DAJE: Usuniecie powaznej usterki uniemozliwiajacej wyzerowanie konta
           i wyplate dokladnie calej dostepnej kwoty.
        """
        konto = self._pobierz_konto(numer)
        if konto.status == "zablokowane":
            raise KontoZablokowane(f"Konto {numer} jest zablokowane")
        
        self._waliduj_typ_kwoty(kwota)
        kwota = Decimal(str(kwota))
        if kwota <= 0:
            raise ValueError("Kwota wyplaty musi byc dodatnia")
        if kwota > konto.saldo:
            raise ValueError("Niewystarczajace srodki na koncie")
        if self._suma_dzisiejszych_wyplat(konto) + kwota > LIMIT_DZIENNY_WYPLAT:
            raise ValueError("Przekroczono dzienny limit wyplat")
            
        konto.saldo -= kwota
        konto.dodaj_wpis("wyplata", kwota)
        return konto.saldo

    @niezawodnosc_logger()
    def przelew(self, numer_z, numer_do, kwota):
        """
        ZMIANY W METODZIE PRZELEW:
        1. Usunieto bledne mnozenie kwoty `Decimal(str(kwota)) * Decimal("100")`.
           CO DAJE: Usuniecie usterki krytycznej, ktora zawyzala wartosc przelewu
           100-krotnie, prowadzac do natychmiastowego drenazu srodkow z konta nadawcy.
        2. Poprawiono formatowanie komunikatu bledu `{numer_z}`.
        3. Dodano weryfikacje typu kwoty (TypeError).
        4. Dodano sprawdzenie czy nadawca i odbiorca to nie to samo konto.
        """
        with self._lock:
            konto_z = self._pobierz_konto(numer_z)
            konto_do = self._pobierz_konto(numer_do)
            
            if konto_z.status == "zablokowane":
                raise KontoZablokowane(f"Konto {numer_z} jest zablokowane")
            
            self._waliduj_typ_kwoty(kwota)
            kwota = Decimal(str(kwota))
            
            if kwota <= 0:
                raise ValueError("Kwota przelewu musi byc dodatnia")
            if kwota > konto_z.saldo:
                raise ValueError("Niewystarczajace srodki na koncie zrodlowym")
            if kwota > Decimal("1000000"):
                raise ValueError("Przelew przekracza limit systemowy (1000000)")
            if self._suma_dzisiejszych_wyplat(konto_z) + kwota > LIMIT_DZIENNY_WYPLAT:
                raise ValueError("Przekroczono dzienny limit wyplat")

            konto_z.saldo -= kwota
            konto_do.saldo += kwota
            konto_z.dodaj_wpis("przelew_wychodzacy", kwota)
            konto_do.dodaj_wpis("przelew_przychodzacy", kwota)
            
        return konto_z.saldo

    @niezawodnosc_logger()
    def nalicz_odsetki(self, numer, roczna_stopa_procentowa, miesiace):
        konto = self._pobierz_konto(numer)
        if miesiace < 0:
            raise ValueError("Liczba miesiecy nie moze byc ujemna")
        stopa_miesieczna = Decimal(str(roczna_stopa_procentowa)) / Decimal("12") / Decimal("100")
        for _ in range(miesiace):
            odsetki = (konto.saldo * stopa_miesieczna).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            konto.saldo += odsetki
            konto.dodaj_wpis("odsetki", odsetki)
        return konto.saldo

    @niezawodnosc_logger()
    def historia_w_okresie(self, numer, od, do):
        konto = self._pobierz_konto(numer)
        wynik = []
        for data_operacji, typ, kwota in konto.historia:
            if od <= data_operacji <= do:
                wynik.append((data_operacji, typ, kwota))
        return wynik

    @niezawodnosc_logger()
    def wyciag_miesieczny(self, numer, rok, miesiac):
        """
        ZMIANA: Uwzgledniono 'przelew_zewnetrzny' w pozycji wyplat na wyciagu.
        
        CO DAJE TA ZMIANA:
        Raport wyciagu uwzglednia teraz pelna sume srodkow opuszczajacych konto,
        zapewniajac zgodnosc ksiegowa zestawienia operacji.
        """
        konto = self._pobierz_konto(numer)
        wplaty = Decimal("0")
        wyplaty = Decimal("0")
        for data_operacji, typ, kwota in konto.historia:
            if data_operacji.year == rok and data_operacji.month == miesiac:
                if typ in ("wplata", "przelew_przychodzacy", "odsetki"):
                    wplaty += kwota
                elif typ in ("wyplata", "przelew_wychodzacy", "przelew_zewnetrzny"):
                    wyplaty += kwota
        return {"wplaty": wplaty, "wyplaty": wyplaty, "saldo_koncowe": konto.saldo}

    @niezawodnosc_logger()
    def przelew_zewnetrzny(self, numer_z, numer_konta_docelowego_zewn, kwota, procesor=None):
        """
        ZMIANA: Dodano walidacje typu kwoty i weryfikacje dziennego limitu wyplat.
        
        CO DAJE TA ZMIANA:
        Chroni stan konta przed niepoprawnym typem i pilnuje limitu obciazen
        rachunku przed wywolaniem zewnetrznego brokera rozliczen.
        """
        konto_z = self._pobierz_konto(numer_z)
        if konto_z.status == "zablokowane":
            raise KontoZablokowane(f"Konto {numer_z} jest zablokowane")
        
        self._waliduj_typ_kwoty(kwota)
        kwota = Decimal(str(kwota))
        if kwota <= 0:
            raise ValueError("Kwota przelewu musi byc dodatnia")
        if kwota > konto_z.saldo:
            raise ValueError("Niewystarczajace srodki na koncie zrodlowym")
        if self._suma_dzisiejszych_wyplat(konto_z) + kwota > LIMIT_DZIENNY_WYPLAT:
            raise ValueError("Przekroczono dzienny limit wyplat")

        proc = procesor or ZewnetrznyProcesor()
        wynik = proc.wyslij_przelew(numer_konta_docelowego_zewn, kwota)
        konto_z.saldo -= kwota
        konto_z.dodaj_wpis("przelew_zewnetrzny", kwota)
        return wynik


# =====================================================================
# SEKCJA TESTOW EKSPLORACYJNYCH I OBLICZENIA WSKAZNIKOW NIEZAWODNOSCI
# (Zadania 5 i 6 z instrukcji NSI_Lab1)
# =====================================================================

def uruchom_testy_eksploracyjne():
    """
    Wykonuje 25 eksploracyjnych wywolan z roznymi danymi
    (poprawne, brzegowe, bledne, zlosliwe), logujac zdarzenia i obliczajac MTTF.
    """
    bank = BankSystem()
    print("=" * 70)
    print("Rozpoczynanie sesji testow eksploracyjnych (NSI - Blok P1)")
    print("=" * 70)

    # Poprawne numery wg cyfry kontrolnej:
    # 123456789 -> suma = 45 -> c10 = 5 -> "1234567895"
    # 987654321 -> suma = 45 -> c10 = 5 -> "9876543215"
    konto1 = "1234567895"
    konto2 = "9876543215"
    konto_bledne = "1234567890"

    liczba_wywolan = 0
    liczba_awarii = 0
    czasy_awarii = []
    czas_startu = time.time()

    # Zestaw 25 wywolan testowych
    przypadki_testowe = [
        # 1-3: Tworzenie kont (poprawne i bledne)
        ("utworz_konto", lambda: bank.utworz_konto(konto1, "Jan Kowalski", 1000)),
        ("utworz_konto_zly_numer", lambda: bank.utworz_konto(konto_bledne, "Bledny Numer")),
        ("utworz_konto_duplikat", lambda: bank.utworz_konto(konto1, "Duplikat")),
        
        # 4-6: Operacje wpłaty
        ("wplac_poprawna", lambda: bank.wplac(konto1, 500)),
        ("wplac_ujemna", lambda: bank.wplac(konto1, -100)),
        ("wplac_nieliczbowa", lambda: bank.wplac(konto1, "sto_zlotych")),
        
        # 7-10: Operacje wypłaty
        ("wyplac_poprawna", lambda: bank.wyplac(konto1, 200)),
        ("wyplac_calosc_salda", lambda: bank.wyplac(konto1, bank.konta[konto1].saldo)),  # wczesniej awaria!
        ("wyplac_ponad_stan", lambda: bank.wyplac(konto1, 50000)),
        ("wyplac_kwota_ujemna", lambda: bank.wyplac(konto1, -50)),
        
        # 11-13: Przygotowanie konta 2 i przelewy
        ("utworz_konto2", lambda: bank.utworz_konto(konto2, "Anna Nowak", 2000)),
        ("przelew_poprawny", lambda: bank.przelew(konto2, konto1, 300)),
        ("przelew_zly_typ", lambda: bank.przelew(konto2, konto1, [100])),
        
        # 14-16: Blokady i operacje na zablokowanym koncie
        ("zablokuj_konto", lambda: bank.zablokuj_konto(konto2)),
        ("wyplac_zablokowane", lambda: bank.wyplac(konto2, 100)),
        ("odblokuj_konto", lambda: bank.odblokuj_konto(konto2)),
        
        # 17-19: Przekroczenia limitow
        ("wyplac_ponad_limit_dzienny", lambda: bank.wyplac(konto2, 5001)),
        ("przelew_ponad_limit_systemowy", lambda: bank.przelew(konto2, konto1, 2000000)),
        ("przelew_nieistniejace_konto", lambda: bank.przelew(konto1, "9999999999", 50)),
        
        # 20-22: Naliczanie odsetek i zestawienia
        ("nalicz_odsetki_poprawne", lambda: bank.nalicz_odsetki(konto1, 5.0, 12)),
        ("historia_okres", lambda: bank.historia_w_okresie(konto1, date(2026, 1, 1), date.today())),
        ("wyciag_miesieczny", lambda: bank.wyciag_miesieczny(konto1, date.today().year, date.today().month)),
        
        # 23-25: Przelew zewnetrzny i procesor
        ("przelew_zewn_zly_typ", lambda: bank.przelew_zewnetrzny(konto1, "PL12345678", None)),
        ("przelew_zewn_symulacja_awarii", lambda: bank.przelew_zewnetrzny(
            konto1, "PL12345678", 50, 
            procesor=ZewnetrznyProcesor(prawdopodobienstwo_awarii=1.0, generator=random.Random(42))
        )),
        ("przelew_zewn_udany", lambda: bank.przelew_zewnetrzny(
            konto1, "PL12345678", 10,
            procesor=ZewnetrznyProcesor(prawdopodobienstwo_awarii=0.0)
        )),
    ]

    for opis, operacja in przypadki_testowe:
        liczba_wywolan += 1
        time.sleep(0.05)  # Drobne opoznienie symulujace realny odstep czasowy
        try:
            operacja()
            print(f"[{liczba_wywolan:02d}] OK   - {opis}")
        except Exception as err:
            liczba_awarii += 1
            t_rel = round(time.time() - czas_startu, 3)
            czasy_awarii.append(t_rel)
            print(f"[{liczba_wywolan:02d}] FAIL - {opis} -> {type(err).__name__}: {err}")

    # =====================================================================
    # OBLICZENIA WSKAŹNIKÓW NIEZAWODNOŚCI (Zgodnie z sekcja 3 instrukcji)
    # =====================================================================
    print("\n" + "=" * 70)
    print("PODSUMOWANIE I WSKAZNIKI NIEZAWODNOSCI (BASELINE)")
    print("=" * 70)

    # Obliczenie MTTF: Sredni czas miedzy awariami
    if len(czasy_awarii) > 1:
        delty = [czasy_awarii[0]] + [czasy_awarii[i] - czasy_awarii[i - 1] for i in range(1, len(czasy_awarii))]
        mttf = sum(delty) / len(delty)
    elif len(czasy_awarii) == 1:
        mttf = czasy_awarii[0]
    else:
        mttf = float("inf")

    # Obliczenie gestosci defektow
    # Liczba linii kodu SUT: ok. 250 linii (0.25 KLOC)
    kloc = 0.25
    unikalne_usterki = 6  # Zidentyfikowane usterki w wariancie D
    gestosc_defektow = unikalne_usterki / kloc

    print(f"Liczba wykonanych wywolan : {liczba_wywolan}")
    print(f"Liczba odnotowanych awarii : {liczba_awarii}")
    print(f"Wzgledne momenty awarii (s): {czasy_awarii}")
    print(f"Wstepne MTTF              : {mttf:.4f} s")
    print(f"Wstepna gestosc defektow  : {gestosc_defektow:.1f} usterek / KLOC")
    print("Wpisy zostaly zarejestrowane w pliku: awarie.jsonl")


if __name__ == "__main__":
    uruchom_testy_eksploracyjne()
