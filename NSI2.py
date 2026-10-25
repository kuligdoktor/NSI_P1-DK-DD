import pytest
from decimal import Decimal
from NSI1 import BankSystem, KontoZablokowane, KontoNieIstnieje

@pytest.fixture
def bank():
    """
    Przygotowuję sobie środowisko testowe. Uruchamiam tę metodę przed każdym testem,
    aby mieć czystą instancję BankSystem z dwoma kontami.
    """
    b = BankSystem()
    b.utworz_konto("1234567895", "Mój Test 1", 5000)
    b.utworz_konto("9876543215", "Mój Test 2", 1000)
    return b

# ==========================================
# 1. TESTY METODY: wplac
# ==========================================
def test_wplac_poprawnie(bank):
    nowe_saldo = bank.wplac("1234567895", 1000)
    assert nowe_saldo == Decimal("6000")
    assert bank.konta["1234567895"].saldo == Decimal("6000")

def test_wplac_niepoprawny_typ(bank):
    with pytest.raises(TypeError, match="Kwota musi byc liczba"):
        bank.wplac("1234567895", "tysiąc")

def test_wplac_ujemna_kwota(bank):
    with pytest.raises(ValueError, match="Kwota wplaty musi byc dodatnia"):
        bank.wplac("1234567895", -50)

def test_wplac_na_nieistniejace_konto(bank):
    with pytest.raises(KontoNieIstnieje):
        bank.wplac("0000000000", 100)

# ==========================================
# 2. TESTY METODY: wyplac
# ==========================================
def test_wyplac_z_zablokowanego(bank):
    bank.zablokuj_konto("1234567895")
    with pytest.raises(KontoZablokowane):
        bank.wyplac("1234567895", 100)

def test_wyplac_ujemna_kwota(bank):
    with pytest.raises(ValueError, match="Kwota wyplaty musi byc dodatnia"):
        bank.wyplac("1234567895", -10)

def test_wyplac_powyzej_salda(bank):
    # Kwota faktycznie przekraczająca saldo 5000
    with pytest.raises(ValueError, match="Niewystarczajace srodki na koncie"):
        bank.wyplac("1234567895", 5001)

def test_wyplac_powyzej_limitu_dziennego(bank):
    # Poprawiona cyfra kontrolna: 9 mod 10 = 9
    bank.utworz_konto("1111111119", "Bogacz", 10000)
    with pytest.raises(ValueError, match="Przekroczono dzienny limit wyplat"):
        bank.wyplac("1111111119", 5001)

def test_wyplac_poprawnie(bank):
    nowe_saldo = bank.wyplac("1234567895", 1000)
    assert nowe_saldo == Decimal("4000")

# ==========================================
# 3. TESTY METODY: przelew
# ==========================================
def test_przelew_zablokowane_zrodlo(bank):
    bank.zablokuj_konto("1234567895")
    with pytest.raises(KontoZablokowane):
        bank.przelew("1234567895", "9876543215", 100)

def test_przelew_ujemna_kwota(bank):
    with pytest.raises(ValueError, match="Kwota przelewu musi byc dodatnia"):
        bank.przelew("1234567895", "9876543215", -50)

def test_przelew_brak_srodkow(bank):
    # Kwota wyższa niż dostępne 1000 na koncie źródłowym
    with pytest.raises(ValueError, match="Niewystarczajace srodki na koncie zrodlowym"):
        bank.przelew("9876543215", "1234567895", 1500)

def test_przelew_ponad_globalny_limit(bank):
    # Poprawiona cyfra kontrolna: 18 mod 10 = 8
    bank.utworz_konto("2222222228", "Bogacz", 2000000)
    with pytest.raises(ValueError, match="Przelew przekracza limit systemowy"):
        bank.przelew("2222222228", "9876543215", 1000001)

def test_przelew_poprawny(bank):
    saldo_po = bank.przelew("1234567895", "9876543215", 10)
    # Po naprawie usterek w kodzie bazowym, odejmuje poprawnie 10
    assert saldo_po == Decimal("4990") 
    assert bank.konta["9876543215"].saldo == Decimal("1010")

############################

# Dodatkowe testy dla utworz_konto
def test_utworz_konto_ujemne_saldo(bank):
    with pytest.raises(ValueError, match="Poczatkowe saldo nie moze byc ujemne"):
        bank.utworz_konto("1111111119", "Jan", -100)

def test_utworz_konto_zerowe_saldo(bank):
    # Konto z saldem zero powinno zostać poprawnie utworzone
    konto = bank.utworz_konto("1111111119", "Zero", 0)
    assert konto.saldo == Decimal("0")
    
    
# Dodatkowe testy dla wpłat i wypłat
def test_wplac_zerowa_kwota(bank):
    with pytest.raises(ValueError, match="Kwota wplaty musi byc dodatnia"):
        bank.wplac("1234567895", 0)

def test_wyplac_zerowa_kwota(bank):
    with pytest.raises(ValueError, match="Kwota wyplaty musi byc dodatnia"):
        bank.wyplac("1234567895", 0)

# Dodatkowy test walidacji numeru
def test_utworz_konto_zly_typ_numeru(bank):
    with pytest.raises(ValueError, match="Nieprawidlowy numer konta lub zla cyfra kontrolna"):
        bank.utworz_konto(1234567895, "Liczba", 100)
    with pytest.raises(ValueError, match="Nieprawidlowy numer konta lub zla cyfra kontrolna"):
        bank.utworz_konto("AB3456789C", "Litery", 100)
