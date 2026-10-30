# Data credits

## SocrateAI NEPSE Open Data
- Source: https://github.com/socrateai-official/nepse-open-data
- Commit / version: 4d0910ac7da2dc2ab3f9f4fd132099562cc33f2b
- Licence: MIT
- Used for: daily floorsheets for 2025-01-01 through 2026-10-16, stored as `Floorsheet/<YYYY-MM-DD>.csv`
- Modified: yes — source columns remapped to this archive's 14-column schema; buyer/seller broker names and security names added from this archive's NEPSE data; `tradeTime`, `tradeBookId` and `stockId` left empty

### MIT licence

MIT License

Copyright (c) 2025 SocrateAI

Permission is hereby granted, free of charge, to any person obtaining a copy
of this dataset and associated documentation files (the "Data"), to deal
in the Data without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Data, and to permit persons to whom the Data is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Data.

THE DATA IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE DATA OR THE USE OR OTHER DEALINGS IN THE DATA.

## MeroLagani Datewise Floorsheet
- Source: https://merolagani.com/FloorSheet.aspx
- Licence: not stated
- Used for: validation only — daily quantity/amount totals and checking whether dates missing from the archive were trading days. No MeroLagani data is stored in this repository.
- Modified: n/a
