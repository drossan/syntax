from datetime import UTC, datetime, timedelta

import jwt
import pytest
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    hash_token,
    new_opaque_token,
    verify_password,
)

SECRET = "x" * 32
NOW = datetime(2026, 1, 1, tzinfo=UTC)
password = "s3cr3t!"


def test_hash_hides_the_password() -> None:
    """El hash difiere del texto plano y usa el esquema Argon2id."""
    hashed = hash_password(password)

    assert hashed != password
    assert hashed.startswith("$argon2id$")


def test_verify_rejects_wrong_password() -> None:
    """La verificación es falsa con una contraseña incorrecta."""
    hashed = hash_password(password)

    assert verify_password("otra", hashed) is False


def test_verify_accepts_correct_password() -> None:
    """La verificación es verdadera con la contraseña correcta."""
    hashed = hash_password(password)

    assert verify_password(password, hashed) is True


def test_same_password_hashes_differ_by_salt() -> None:
    """Dos hashes de la misma contraseña difieren (salt) y ambos verifican."""
    h1 = hash_password(password)
    h2 = hash_password(password)

    assert h1 != h2
    assert verify_password(password, h1) is True
    assert verify_password(password, h2) is True


def test_verify_is_fail_closed_against_malformed_hash() -> None:
    """Un hash malformado (vacío o no-Argon2id) → False, sin propagar excepción."""
    assert verify_password("X", "") is False
    assert verify_password("X", "no-es-un-hash") is False


def test_empty_password_is_its_own_class() -> None:
    """La contraseña vacía se hashea y solo verifica contra "" (clase propia)."""
    hashed = hash_password("")

    assert verify_password("", hashed) is True
    assert verify_password("no-vacia", hashed) is False


def test_access_token_round_trip() -> None:
    """El token decodifica a los mismos sub/tenant_id, sin claim de capacidades."""
    token = create_access_token(
        "user-1", "tenant-1", secret=SECRET, algorithm="HS256", ttl=900, now=NOW
    )

    claims = decode_access_token(token, secret=SECRET, algorithm="HS256", now=NOW)

    assert claims["sub"] == "user-1"
    assert claims["tenant_id"] == "tenant-1"
    assert "capabilities" not in claims


def test_exp_is_now_plus_ttl() -> None:
    """iat = now, exp = now + ttl (segundos Unix)."""
    token = create_access_token("u", "t", secret=SECRET, algorithm="HS256", ttl=900, now=NOW)

    claims = decode_access_token(token, secret=SECRET, algorithm="HS256", now=NOW)

    assert claims["iat"] == int(NOW.timestamp())
    assert claims["exp"] == int(NOW.timestamp()) + 900


def test_invalid_signature_is_rejected() -> None:
    """Un token firmado con otro secreto se rechaza."""
    token = create_access_token("u", "t", secret=SECRET, algorithm="HS256", ttl=900, now=NOW)

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token, secret="y" * 32, algorithm="HS256", now=NOW)


def test_alg_none_is_rejected() -> None:
    """Un token con alg=none (sin firma) se rechaza al exigir algorithms=[HS256]."""
    forged = jwt.encode(
        {"sub": "u", "tenant_id": "t", "exp": int(NOW.timestamp()) + 900},
        "",
        algorithm="none",
    )

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(forged, secret=SECRET, algorithm="HS256", now=NOW)


def test_algorithm_confusion_is_rejected() -> None:
    """Un token firmado con HS384 se rechaza cuando se exige HS256."""
    forged = jwt.encode(
        {"sub": "u", "tenant_id": "t", "exp": int(NOW.timestamp()) + 900},
        "x" * 48,
        algorithm="HS384",
    )

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(forged, secret=SECRET, algorithm="HS256", now=NOW)


def test_token_missing_required_claim_is_rejected() -> None:
    """Un token bien firmado pero sin tenant_id se rechaza."""
    incomplete = jwt.encode(
        {"sub": "u", "exp": int(NOW.timestamp()) + 900},
        SECRET,
        algorithm="HS256",
    )

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(incomplete, secret=SECRET, algorithm="HS256", now=NOW)


@pytest.mark.parametrize("garbage", ["no.es.jwt", ""])
def test_non_jwt_string_is_rejected(garbage: str) -> None:
    """Una cadena que no es un JWT se rechaza (error de parseo)."""
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(garbage, secret=SECRET, algorithm="HS256", now=NOW)


def test_expired_token_is_rejected() -> None:
    """Un token cuyo exp es anterior al now de decodificación se rechaza."""
    token = create_access_token("u", "t", secret=SECRET, algorithm="HS256", ttl=900, now=NOW)
    later = NOW + timedelta(seconds=901)

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token, secret=SECRET, algorithm="HS256", now=later)


@pytest.mark.parametrize(
    ("decode_offset", "should_be_valid"),
    [
        (-1, True),  # now 1s antes de exp  → válido
        (0, False),  # now == exp           → expirado
        (1, False),  # now 1s después de exp → expirado
    ],
)
def test_expiration_boundary(decode_offset: int, should_be_valid: bool) -> None:
    """Frontera: válido solo si now < exp (now == exp → expirado)."""
    token = create_access_token("u", "t", secret=SECRET, algorithm="HS256", ttl=900, now=NOW)
    exp_time = NOW + timedelta(seconds=900)
    decode_now = exp_time + timedelta(seconds=decode_offset)

    if should_be_valid:
        claims = decode_access_token(token, secret=SECRET, algorithm="HS256", now=decode_now)
        assert claims["sub"] == "u"
    else:
        with pytest.raises(jwt.ExpiredSignatureError):
            decode_access_token(token, secret=SECRET, algorithm="HS256", now=decode_now)


def test_decode_uses_real_clock_when_now_is_none_accepts_far_future() -> None:
    """Sin now, valida contra el reloj real: un exp a siglos vista es válido."""
    token = create_access_token(
        "u", "t", secret=SECRET, algorithm="HS256", ttl=10_000_000_000, now=NOW
    )

    claims = decode_access_token(token, secret=SECRET, algorithm="HS256")  # now=None

    assert claims["sub"] == "u"


def test_decode_uses_real_clock_when_now_is_none_rejects_past() -> None:
    """Sin now, un exp muy en el pasado se rechaza contra el reloj real."""
    past = datetime(2000, 1, 1, tzinfo=UTC)
    token = create_access_token("u", "t", secret=SECRET, algorithm="HS256", ttl=1, now=past)

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token, secret=SECRET, algorithm="HS256")  # now=None


def test_create_access_token_secret_is_keyword_only() -> None:
    """secret/algorithm/ttl/now son keyword-only: pasarlos por posición es TypeError."""
    with pytest.raises(TypeError):
        create_access_token("u", "t", "secret", "HS256", 900, NOW)  # posicional → viola el contrato


def test_decode_access_token_secret_is_keyword_only() -> None:
    """secret/algorithm son keyword-only en decode: pasarlos por posición es TypeError."""
    token = create_access_token("u", "t", secret=SECRET, algorithm="HS256", ttl=900, now=NOW)
    with pytest.raises(TypeError):
        decode_access_token(token, SECRET, "HS256")  # posicional → viola el contrato


def test_new_opaque_token_has_enough_entropy() -> None:
    """new_opaque_token() genera un token largo y distinto en cada llamada (256 bits)."""
    token_a = new_opaque_token()
    token_b = new_opaque_token()
    assert token_a != token_b
    assert len(token_a) >= 32


def test_hash_token_is_deterministic() -> None:
    """hash_token() es determinista: mismo input, mismo hash (buscable por igualdad)."""
    token = new_opaque_token()
    assert hash_token(token) == hash_token(token)


def test_hash_token_differs_from_hash_password() -> None:
    """hash_token NO es hash_password: mismo input, hashes distintos (SHA-256 vs Argon2id)."""
    token = "some-opaque-token"
    assert hash_token(token) != hash_password(token)


def test_hash_token_different_inputs_differ() -> None:
    """Dos tokens distintos producen hashes distintos."""
    assert hash_token(new_opaque_token()) != hash_token(new_opaque_token())
