import base64
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import pymupdf

from extrator_dados_crlv import (
    Base64InvalidoError,
    CRLVInvalidoError,
    CRLVProtegidoError,
    CRLVSemTextoError,
    DadosVeiculo,
    ErroCRLV,
    extrair_dados,
    extrair_dados_base64,
    extrair_dados_bytes,
)
from extrator_dados_crlv.cli import main

RAIZ = Path(__file__).resolve().parents[1]


def _criar_crlv_sintetico() -> bytes:
    """Gera um CRLV de teste com dados fictícios, sem depender de PDF externo."""
    campos = [
        ("CÓDIGO RENAVAM", "12345678901", 31, 90),
        ("PLACA", "ABC1D23", 31, 130),
        ("EXERCÍCIO", "2026", 103, 130),
        ("ANO FABRICAÇÃO", "2022", 31, 190),
        ("ANO MODELO", "2023", 103, 190),
        ("NÚMERO DO CRV", "123456789012", 31, 250),
        ("MARCA / MODELO / VERSÃO", "MARCA/TESTE 1.0", 31, 310),
        ("ESPÉCIE / TIPO", "MISTO UTILITARIO", 31, 370),
        ("PLACA ANTERIOR / UF", "XYZ9Z99/CE", 31, 430),
        ("CHASSI", "9BRK3AAG9P0000000", 160, 430),
        ("COR PREDOMINANTE", "PRATA", 31, 490),
        ("COMBUSTÍVEL", "ALCOOL/GASOLINA", 103, 490),
        ("CATEGORIA", "PARTICULAR", 317, 90),
        ("LOCAL", "FORTALEZA CE", 317, 250),
        ("DATA", "01/01/2026", 510, 250),
        ("NOME", "EMPRESA TESTE LTDA", 317, 190),
        ("CPF / CNPJ", "00.000.000/0001-00", 463, 220),
    ]

    with pymupdf.open() as documento:
        pagina = documento.new_page(width=595, height=842)
        for rotulo, valor, x, y in campos:
            pagina.insert_text((x, y), rotulo, fontsize=8)
            pagina.insert_text((x, y + 15), valor, fontsize=10)
        return documento.tobytes()


def _pdf_sem_texto() -> bytes:
    with pymupdf.open() as documento:
        documento.new_page()
        return documento.tobytes()


def _pdf_com_texto_qualquer() -> bytes:
    with pymupdf.open() as documento:
        pagina = documento.new_page()
        pagina.insert_text((72, 72), "Documento sem dados de veiculo", fontsize=12)
        return documento.tobytes()


def _pdf_apenas_valores() -> bytes:
    """PDF sem rótulos, para exercitar a busca por padrão no documento inteiro."""
    with pymupdf.open() as documento:
        pagina = documento.new_page()
        pagina.insert_text((72, 72), "ABC1D23", fontsize=12)
        pagina.insert_text((72, 100), "9BRK3AAG9P0000000", fontsize=12)
        return documento.tobytes()


def _pdf_com_placa_anterior() -> bytes:
    with pymupdf.open() as documento:
        pagina = documento.new_page()
        pagina.insert_text((72, 72), "PLACA ANTERIOR / UF XYZ9Z99/CE", fontsize=12)
        pagina.insert_text((72, 100), "ABC1D23", fontsize=12)
        pagina.insert_text((72, 130), "9BRK3AAG9P0000000", fontsize=12)
        return documento.tobytes()


def _pdf_protegido() -> bytes:
    with pymupdf.open() as documento:
        documento.new_page()
        return documento.tobytes(
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            owner_pw="senha",
            user_pw="senha",
        )


PDF_SINTETICO = _criar_crlv_sintetico()
PDF_BASE64 = base64.b64encode(PDF_SINTETICO).decode("ascii")


class TestExtracao(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dados = extrair_dados_bytes(PDF_SINTETICO)

    def test_placa(self) -> None:
        self.assertEqual(self.dados.placa, "ABC1D23")

    def test_chassi(self) -> None:
        self.assertEqual(self.dados.chassi, "9BRK3AAG9P0000000")

    def test_dados_complementares(self) -> None:
        self.assertEqual(self.dados.renavam, "12345678901")
        self.assertEqual(self.dados.numero_crv, "123456789012")
        self.assertEqual(self.dados.exercicio, "2026")
        self.assertEqual(self.dados.marca_modelo, "MARCA/TESTE 1.0")
        self.assertEqual(self.dados.ano_fabricacao, "2022")
        self.assertEqual(self.dados.ano_modelo, "2023")
        self.assertEqual(self.dados.cor, "PRATA")
        self.assertEqual(self.dados.combustivel, "ALCOOL/GASOLINA")
        self.assertEqual(self.dados.categoria, "PARTICULAR")
        self.assertEqual(self.dados.especie_tipo, "MISTO UTILITARIO")
        self.assertEqual(self.dados.local, "FORTALEZA CE")
        self.assertEqual(self.dados.proprietario, "EMPRESA TESTE LTDA")
        self.assertEqual(self.dados.cpf_cnpj, "00.000.000/0001-00")

    def test_modelo(self) -> None:
        self.assertIsInstance(self.dados, DadosVeiculo)
        self.assertTrue(self.dados.completo)
        self.assertEqual(self.dados.arquivo, "<bytes>")
        self.assertEqual(self.dados.para_dict()["placa"], "ABC1D23")

    def test_texto_sem_dados_retorna_incompleto(self) -> None:
        dados = extrair_dados_bytes(_pdf_com_texto_qualquer())
        self.assertFalse(dados.completo)
        self.assertIsNone(dados.placa)
        self.assertIsNone(dados.chassi)

    def test_fallback_quando_rotulos_nao_existem(self) -> None:
        dados = extrair_dados_bytes(_pdf_apenas_valores())
        self.assertEqual(dados.placa, "ABC1D23")
        self.assertEqual(dados.chassi, "9BRK3AAG9P0000000")
        self.assertTrue(dados.completo)

    def test_fallback_ignora_placa_anterior(self) -> None:
        dados = extrair_dados_bytes(_pdf_com_placa_anterior())
        self.assertEqual(dados.placa, "ABC1D23")
        self.assertEqual(dados.chassi, "9BRK3AAG9P0000000")


class TestEntradaBase64(unittest.TestCase):
    def test_base64(self) -> None:
        dados = extrair_dados_base64(PDF_BASE64)
        self.assertEqual(dados.placa, "ABC1D23")
        self.assertEqual(dados.chassi, "9BRK3AAG9P0000000")
        self.assertEqual(dados.arquivo, "<base64>")
        self.assertTrue(dados.completo)

    def test_base64_em_bytes(self) -> None:
        dados = extrair_dados_base64(PDF_BASE64.encode("ascii"))
        self.assertEqual(dados.placa, "ABC1D23")

    def test_base64_com_flag(self) -> None:
        dados = extrair_dados(PDF_BASE64, base64=True)
        self.assertEqual(dados.placa, "ABC1D23")
        self.assertEqual(dados.chassi, "9BRK3AAG9P0000000")

    def test_base64_com_bom(self) -> None:
        dados = extrair_dados_base64(b"\xef\xbb\xbf" + PDF_BASE64.encode("ascii"))
        self.assertEqual(dados.placa, "ABC1D23")

    def test_data_uri(self) -> None:
        dados = extrair_dados_base64("data:application/pdf;base64," + PDF_BASE64)
        self.assertEqual(dados.placa, "ABC1D23")

    def test_base64_urlsafe_sem_padding(self) -> None:
        url_safe = base64.urlsafe_b64encode(PDF_SINTETICO).decode("ascii")
        dados = extrair_dados_base64(url_safe.rstrip("="))
        self.assertEqual(dados.placa, "ABC1D23")


class TestEntradaBinaria(unittest.TestCase):
    def test_pdf_em_bytes(self) -> None:
        dados = extrair_dados_bytes(PDF_SINTETICO)
        self.assertEqual(dados.placa, "ABC1D23")
        self.assertEqual(dados.chassi, "9BRK3AAG9P0000000")
        self.assertEqual(dados.arquivo, "<bytes>")

    def test_pdf_em_bytearray(self) -> None:
        dados = extrair_dados(bytearray(PDF_SINTETICO))
        self.assertEqual(dados.placa, "ABC1D23")

    def test_pdf_em_memoryview(self) -> None:
        dados = extrair_dados(memoryview(PDF_SINTETICO))
        self.assertEqual(dados.placa, "ABC1D23")


class TestErros(unittest.TestCase):
    def test_arquivo_inexistente(self) -> None:
        with self.assertRaises(FileNotFoundError):
            extrair_dados(RAIZ / "nao-existe.pdf")

    def test_caminho_nao_e_arquivo(self) -> None:
        with self.assertRaises(IsADirectoryError):
            extrair_dados(RAIZ)

    def test_base64_invalido(self) -> None:
        with self.assertRaises(Base64InvalidoError):
            extrair_dados_base64("isto não é base64")

    def test_base64_de_outro_conteudo(self) -> None:
        with self.assertRaises(Base64InvalidoError):
            extrair_dados_base64(base64.b64encode(b"apenas texto").decode("ascii"))

    def test_pdf_invalido_em_bytes(self) -> None:
        with self.assertRaises(CRLVInvalidoError):
            extrair_dados_bytes(b"isto nao e um pdf")

    def test_pdf_sem_texto(self) -> None:
        with self.assertRaises(CRLVSemTextoError):
            extrair_dados_bytes(_pdf_sem_texto())

    def test_pdf_protegido(self) -> None:
        with self.assertRaises(CRLVProtegidoError):
            extrair_dados_bytes(_pdf_protegido())

    def test_tipo_de_origem_invalido(self) -> None:
        with self.assertRaises(TypeError):
            extrair_dados(123)  # type: ignore[arg-type]

    def test_base64_com_path(self) -> None:
        with self.assertRaises(TypeError):
            extrair_dados(RAIZ / "arquivo.pdf", base64=True)

    def test_excecoes_sao_erro_crlv(self) -> None:
        self.assertTrue(issubclass(Base64InvalidoError, ErroCRLV))
        self.assertTrue(issubclass(Base64InvalidoError, ValueError))
        self.assertTrue(issubclass(CRLVProtegidoError, CRLVInvalidoError))
        self.assertTrue(issubclass(CRLVSemTextoError, CRLVInvalidoError))


class TestCLI(unittest.TestCase):
    def setUp(self) -> None:
        self._diretorio = tempfile.TemporaryDirectory()
        self.arquivo = Path(self._diretorio.name) / "crlv.pdf"
        self.arquivo.write_bytes(PDF_SINTETICO)

    def tearDown(self) -> None:
        self._diretorio.cleanup()

    def test_cli_arquivo_json(self) -> None:
        saida = io.StringIO()
        with redirect_stdout(saida):
            codigo = main([str(self.arquivo), "--json"])
        self.assertEqual(codigo, 0)
        payload = json.loads(saida.getvalue())
        self.assertEqual(payload["placa"], "ABC1D23")
        self.assertEqual(payload["chassi"], "9BRK3AAG9P0000000")

    def test_cli_base64_json(self) -> None:
        saida = io.StringIO()
        with redirect_stdout(saida):
            codigo = main(["--base64", PDF_BASE64, "--json"])
        self.assertEqual(codigo, 0)
        payload = json.loads(saida.getvalue())
        self.assertEqual(payload["placa"], "ABC1D23")
        self.assertEqual(payload["chassi"], "9BRK3AAG9P0000000")


if __name__ == "__main__":
    unittest.main()
