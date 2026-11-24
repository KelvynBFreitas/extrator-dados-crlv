import base64
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pymupdf

from extrator_dados_crlv import (
    Base64InvalidoError,
    CRLVInvalidoError,
    CRLVProtegidoError,
    CRLVSemTextoError,
    DadosVeiculo,
    ErroCRLV,
    OCRError,
    OCRIndisponivelError,
    aplicar_ocr,
    extrair_dados,
    extrair_dados_base64,
    extrair_dados_base64_robusto,
    extrair_dados_bytes,
    extrair_dados_robusto,
)
from extrator_dados_crlv import crlv as modulo_crlv
from extrator_dados_crlv import ocr as modulo_ocr
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

TEM_OCR = (
    importlib.util.find_spec("rapidocr_onnxruntime") is not None
    or importlib.util.find_spec("rapidocr") is not None
)


def _pdf_digitalizado() -> bytes:
    """Rasteriza o CRLV sintético para simular um PDF escaneado (sem texto)."""
    with pymupdf.open(stream=PDF_SINTETICO, filetype="pdf") as original:
        pix = original[0].get_pixmap(dpi=300)

    with pymupdf.open() as documento:
        pagina = documento.new_page(width=595, height=842)
        pagina.insert_image(pagina.rect, stream=pix.tobytes("png"))
        return documento.tobytes()


class _EngineOCRSimulado:
    """Imita a saída do RapidOCR com coordenadas em pixels (300 dpi)."""

    def __init__(self, dpi: int = 300) -> None:
        self.fator = dpi / 72.0

    def _caixa(self, x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
        return [
            [x0 * self.fator, y0 * self.fator],
            [x1 * self.fator, y0 * self.fator],
            [x1 * self.fator, y1 * self.fator],
            [x0 * self.fator, y1 * self.fator],
        ]

    def __call__(
        self, imagem: object
    ) -> tuple[list[tuple[list[list[float]], str, float]], list[float]]:
        return [
            (self._caixa(31, 120, 70, 133), "PLACA", 1.0),
            (self._caixa(31, 135, 100, 150), "ABC1D23", 1.0),
            (self._caixa(160, 420, 210, 433), "CHASSI", 1.0),
            (self._caixa(160, 435, 300, 450), "9BRK3AAG9P0000000", 1.0),
        ], [0.0]


class _EngineOCRSimuladoV3(_EngineOCRSimulado):
    """Imita a saída do rapidocr >= 3 (objeto com boxes/txts/scores)."""

    def __call__(self, imagem: object) -> SimpleNamespace:
        itens, _ = super().__call__(imagem)
        return SimpleNamespace(
            boxes=[item[0] for item in itens],
            txts=[item[1] for item in itens],
            scores=[item[2] for item in itens],
        )


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


class TestOCR(unittest.TestCase):
    def test_aplicar_ocr_pdf_invalido(self) -> None:
        with self.assertRaises(CRLVInvalidoError):
            aplicar_ocr(b"isto nao e um pdf")

    def test_aplicar_ocr_pdf_protegido(self) -> None:
        with self.assertRaises(CRLVProtegidoError):
            aplicar_ocr(_pdf_protegido())

    def test_aplicar_ocr_dpi_invalido(self) -> None:
        with self.assertRaises(ValueError):
            aplicar_ocr(_pdf_sem_texto(), dpi=10)
        with self.assertRaises(TypeError):
            aplicar_ocr(_pdf_sem_texto(), dpi=True)  # type: ignore[arg-type]

    def test_aplicar_ocr_sem_dependencia(self) -> None:
        with (
            mock.patch.object(modulo_ocr, "_engine", None),
            mock.patch.object(
                modulo_ocr,
                "_carregar_engine",
                side_effect=OCRIndisponivelError("indisponível"),
            ),
            self.assertRaises(OCRIndisponivelError),
        ):
            aplicar_ocr(_pdf_sem_texto())

    def test_aplicar_ocr_injeta_texto(self) -> None:
        with mock.patch.object(modulo_ocr, "_engine", _EngineOCRSimulado()):
            pdf_com_texto = aplicar_ocr(_pdf_sem_texto(), dpi=300)

        dados = extrair_dados_bytes(pdf_com_texto)
        self.assertEqual(dados.placa, "ABC1D23")
        self.assertEqual(dados.chassi, "9BRK3AAG9P0000000")

    def test_aplicar_ocr_com_saida_do_rapidocr_v3(self) -> None:
        with mock.patch.object(modulo_ocr, "_engine", _EngineOCRSimuladoV3()):
            pdf_com_texto = aplicar_ocr(_pdf_sem_texto(), dpi=300)

        dados = extrair_dados_bytes(pdf_com_texto)
        self.assertEqual(dados.placa, "ABC1D23")
        self.assertEqual(dados.chassi, "9BRK3AAG9P0000000")

    def test_aplicar_ocr_sem_texto_reconhecido(self) -> None:
        engine = mock.Mock(return_value=(None, None))
        with (
            mock.patch.object(modulo_ocr, "_engine", engine),
            self.assertRaises(CRLVSemTextoError),
        ):
            aplicar_ocr(_pdf_sem_texto())

    def test_robusto_com_arquivo(self) -> None:
        with tempfile.TemporaryDirectory() as diretorio:
            arquivo = Path(diretorio) / "digitalizado.pdf"
            arquivo.write_bytes(_pdf_sem_texto())

            with mock.patch.object(
                modulo_crlv, "aplicar_ocr", return_value=PDF_SINTETICO
            ) as aplicar:
                dados = extrair_dados_robusto(arquivo)

        self.assertEqual(dados.placa, "ABC1D23")
        self.assertEqual(dados.chassi, "9BRK3AAG9P0000000")
        self.assertTrue(dados.completo)
        aplicar.assert_called_once()
        self.assertEqual(aplicar.call_args.kwargs["dpi"], 300)

    def test_robusto_com_base64(self) -> None:
        conteudo = base64.b64encode(_pdf_sem_texto()).decode("ascii")

        with mock.patch.object(modulo_crlv, "aplicar_ocr", return_value=PDF_SINTETICO) as aplicar:
            dados = extrair_dados_base64_robusto(conteudo)

        self.assertEqual(dados.placa, "ABC1D23")
        self.assertEqual(dados.chassi, "9BRK3AAG9P0000000")
        self.assertEqual(dados.arquivo, "<base64>")
        aplicar.assert_called_once()

    def test_flag_ocr_na_api_unificada(self) -> None:
        conteudo = base64.b64encode(_pdf_sem_texto()).decode("ascii")

        with mock.patch.object(modulo_crlv, "aplicar_ocr", return_value=PDF_SINTETICO):
            dados = extrair_dados(conteudo, base64=True, ocr=True)

        self.assertEqual(dados.placa, "ABC1D23")
        self.assertEqual(dados.arquivo, "<base64>")

    def test_sem_ocr_continua_levantando_erro(self) -> None:
        with self.assertRaises(CRLVSemTextoError):
            extrair_dados_bytes(_pdf_sem_texto())

    def test_erro_quando_ocr_nao_reconhece_texto(self) -> None:
        with (
            mock.patch.object(
                modulo_crlv,
                "aplicar_ocr",
                side_effect=CRLVSemTextoError("sem texto"),
            ),
            self.assertRaises(CRLVSemTextoError),
        ):
            extrair_dados_robusto(_pdf_sem_texto())

    def test_erro_de_ocr_nao_e_mascarado(self) -> None:
        with (
            mock.patch.object(
                modulo_crlv,
                "aplicar_ocr",
                side_effect=OCRError("falha no OCR"),
            ),
            self.assertRaises(OCRError),
        ):
            extrair_dados_robusto(_pdf_sem_texto())

    @unittest.skipUnless(TEM_OCR, "extra de OCR não instalado")
    def test_integracao_ocr_real(self) -> None:
        dados = extrair_dados_bytes(_pdf_digitalizado(), ocr=True)
        self.assertEqual(dados.placa, "ABC1D23")
        self.assertEqual(dados.chassi, "9BRK3AAG9P0000000")


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

    def test_cli_ocr(self) -> None:
        dados = extrair_dados_bytes(PDF_SINTETICO)

        with (
            mock.patch("extrator_dados_crlv.cli.extrair_dados", return_value=dados) as extrair,
            redirect_stdout(io.StringIO()),
        ):
            codigo = main([str(self.arquivo), "--ocr", "--json"])

        self.assertEqual(codigo, 0)
        self.assertTrue(extrair.call_args.kwargs["ocr"])


if __name__ == "__main__":
    unittest.main()
