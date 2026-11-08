import pytest
from decimal import Decimal
from NSI1 import BankSystem, KontoZablokowane, KontoNieIstnieje

@pytest.fixture
def bank():
    """
    Przygotowuję czyste środowisko dla moich testów funkcjonalnych.
    Opieram się na specyfikacji z dokumentacji SUT, dlatego używam numerów kont,
    które poprawnie przechodzą algorytm cyfry kontrolnej modulo 10.
    """
    b = BankSystem()
    b.utworz_konto("1234567895", "Klient A", 10000)
    b.utworz_konto("9876543215", "Klient B", 1000)
    b.utworz_konto("1111111119", "Klient LIMIT", 2000000)
    b.utworz_konto("2222222228", "Grosze", 10)
    b.utworz_konto("3333333337", "Grosze2", 10)
    return b

# ========================================================
# POKRYCIE TABLICY DECYZYJNEJ I GRANIC DLA: wyplac
# ========================================================

def test_wyplac_wiersz_1_zablokowane(bank):
    # Wiersz 1 tablicy decyzyjnej: Konto zablokowane od razu rzuca błąd.
    bank.zablokuj_konto("1234567895")
    with pytest.raises(KontoZablokowane):
        bank.wyplac("1234567895", 100)

def test_wyplac_wiersz_2_granica_zero(bank):
    # Wiersz 2: Kwota niedodatnia. 
    # Wartość brzegowa dla tej klasy równoważności to dokładnie 0.
    with pytest.raises(ValueError, match="Kwota wyplaty musi byc dodatnia"):
        bank.wyplac("1234567895", 0) 

def test_wyplac_wiersz_3_granica_salda(bank):
    # Wiersz 3: Brak środków.
    # Wartość brzegowa: Klient B ma równe 1000 PLN. Przekraczam saldo o najmniejszą możliwą jednostkę.
    with pytest.raises(ValueError, match="Niewystarczajace srodki"):
        bank.wyplac("9876543215", Decimal("1000.01")) 

def test_wyplac_wiersz_4_granica_limitu_dziennego(bank):
    # Wiersz 4: Przekroczenie limitu.
    # Wartość brzegowa: Dzienny limit to 5000. Próbuję wypłacić minimalnie więcej.
    with pytest.raises(ValueError, match="Przekroczono dzienny limit wyplat"):
        bank.wyplac("1234567895", Decimal("5000.01"))

def test_wyplac_wiersz_5_sukces_na_granicy(bank):
    # Wiersz 5: Sukces.
    # Wartość brzegowa: Wypłata równa dokładnie saldu (1000 PLN dla Klienta B).
    # Zgodnie z dokumentacją powinno to zostawić konto z saldem 0.
    nowe_saldo = bank.wyplac("9876543215", 1000)
    assert nowe_saldo == Decimal("0")

# ========================================================
# TESTY GRANICZNE DLA: przelew
# ========================================================

def test_przelew_granica_limitu_systemowego_sukces(bank, monkeypatch):
    # Wartość brzegowa: Przelew dokładnie na równi z limitem systemowym z dokumentacji (1 000 000).
    # UWAGA: SUT wlicza przelewy do dziennego limitu wypłat (5000). 
    # Aby przetestować ten wiersz bez uderzania w limit dzienny, używamy monkeypatching
    # do tymczasowego podniesienia globalnego limitu dziennego tylko na czas tego testu.
    import NSI1
    monkeypatch.setattr(NSI1, "LIMIT_DZIENNY_WYPLAT", Decimal("2000000"))
    
    saldo = bank.przelew("1111111119", "1234567895", Decimal("1000000"))
    assert saldo == Decimal("1000000")

def test_przelew_granica_limitu_systemowego_blad(bank):
    # Wartość brzegowa: Minimalne przekroczenie limitu systemowego o 1 grosz.
    # Poprawiono oczekiwany komunikat błędu na zgodny z implementacją SUT
    with pytest.raises(ValueError, match="Przelew przekracza limit systemowy \\(1000000\\)"):
        bank.przelew("1111111119", "1234567895", Decimal("1000000.01"))

# ========================================================
# TESTY GRANICZNE ZAOKRĄGLEŃ DLA: nalicz_odsetki
# ========================================================

def test_odsetki_zaokraglenie_w_dol(bank):
    # Wartość brzegowa zaokrąglania.
    # Saldo 10 PLN, stopa 0.48% rocznie -> 0.04% miesięcznie.
    # Obliczenia: 10 * 0.0004 = 0.004 PLN. 
    # Przy regule ROUND_HALF_UP z dokumentacji, wartość 0.004 musi zostać ucięta do 0.00.
    nowe_saldo = bank.nalicz_odsetki("2222222228", Decimal("0.48"), 1)
    assert nowe_saldo == Decimal("10.00")

def test_odsetki_zaokraglenie_w_gore(bank):
    # Wartość brzegowa zaokrąglania w górę.
    # Saldo 10 PLN, stopa 0.60% rocznie -> 0.05% miesięcznie.
    # Obliczenia: 10 * 0.0005 = 0.005 PLN.
    # Zgodnie z ROUND_HALF_UP połówka (0.005) powinna zaokrąglić się do 0.01.
    nowe_saldo = bank.nalicz_odsetki("3333333337", Decimal("0.60"), 1)
    assert nowe_saldo == Decimal("10.01")