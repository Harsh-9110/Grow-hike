import io

import pytest
from fastapi import HTTPException
from openpyxl import Workbook

from app.services.imports import read_rows


def test_utf8_bom_csv_is_accepted():
    rows = read_rows(b'\xef\xbb\xbfsymbol,quantity,average_price\nAAPL,2,100\n','sample.csv')
    assert rows[0]['symbol'] == 'AAPL'


def test_xlsx_reads_the_first_sheet_without_external_links():
    workbook = Workbook()
    workbook.active.append(['symbol','quantity','average_price'])
    workbook.active.append(['AAPL',2,'100.25'])
    buffer = io.BytesIO()
    workbook.save(buffer)
    rows = read_rows(buffer.getvalue(),'sample.xlsx')
    assert rows[0]['average_price'] == '100.25'


@pytest.mark.parametrize('content,name',[(b'','empty.csv'),(b'not a zip','bad.xlsx'),(b'anything','bad.xls')])
def test_bad_files_are_validation_errors(content,name):
    with pytest.raises(HTTPException) as e:
        read_rows(content,name)
    assert e.value.status_code == 422


def test_oversized_upload_is_rejected():
    with pytest.raises(HTTPException) as e:
        read_rows(b'x'*(2*1024*1024+1),'big.csv')
    assert e.value.status_code == 413
