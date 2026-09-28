#!/usr/bin/env python3
"""
Generate a native Microsoft Visio (.vsdx) file for the ACDE System Architecture.
Follows the official ISO/IEC 29500-1 and Microsoft Visio 2012+ OpenXML standard.
"""

import os
import zipfile
from PIL import Image

def generate_vsdx(png_path="docs/system_architecture.png", out_vsdx="docs/system_architecture.vsdx"):
    if not os.path.exists(png_path):
        raise FileNotFoundError(f"Source PNG not found at: {png_path}")
        
    with Image.open(png_path) as im:
        w_px, h_px = im.size
        
    dpi = 300
    w_in = w_px / dpi
    h_in = h_px / dpi
    page_w = round(w_in + 0.6, 2)
    page_h = round(h_in + 0.6, 2)
    pin_x = round(page_w / 2.0, 2)
    pin_y = round(page_h / 2.0, 2)
    loc_pin_x = round(w_in / 2.0, 2)
    loc_pin_y = round(h_in / 2.0, 2)
    
    with open(png_path, "rb") as f:
        png_bytes = f.read()

    files = {}

    files["[Content_Types].xml"] = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="png" ContentType="image/png"/>
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/visio/document.xml" ContentType="application/vnd.ms-visio.drawing.main+xml"/>
  <Override PartName="/visio/pages/pages.xml" ContentType="application/vnd.ms-visio.pages+xml"/>
  <Override PartName="/visio/pages/page1.xml" ContentType="application/vnd.ms-visio.page+xml"/>
  <Override PartName="/visio/windows.xml" ContentType="application/vnd.ms-visio.windows+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""

    files["_rels/.rels"] = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/document" Target="visio/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""

    files["docProps/core.xml"] = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>ACDE System Architecture</dc:title>
  <dc:creator>ACDE Framework</dc:creator>
</cp:coreProperties>"""

    files["docProps/app.xml"] = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
  <Application>Microsoft Visio</Application>
</Properties>"""

    files["visio/_rels/document.xml.rels"] = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/pages" Target="pages/pages.xml"/>
  <Relationship Id="rId2" Type="http://schemas.microsoft.com/visio/2010/relationships/windows" Target="windows.xml"/>
</Relationships>"""

    files["visio/document.xml"] = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<VisioDocument xmlns="http://schemas.microsoft.com/office/visio/2012/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xml:space="preserve">
  <DocumentSettings>
    <GlueSettings>9</GlueSettings>
    <SnapSettings>65</SnapSettings>
    <SnapExtensions>34</SnapExtensions>
  </DocumentSettings>
  <Colors>
    <ColorEntry IX="0" RGB="#000000"/>
    <ColorEntry IX="1" RGB="#FFFFFF"/>
  </Colors>
  <FaceNames/>
  <StyleSheets/>
  <DocumentSheet/>
</VisioDocument>"""

    files["visio/windows.xml"] = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Windows xmlns="http://schemas.microsoft.com/office/visio/2012/main">
  <Window ID="0" WindowType="Drawing" WindowState="1073741824">
    <ShowRulers>1</ShowRulers>
    <ShowGrid>1</ShowGrid>
    <ShowPageBreaks>0</ShowPageBreaks>
    <ShowGuides>1</ShowGuides>
  </Window>
</Windows>"""

    files["visio/pages/_rels/pages.xml.rels"] = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/page" Target="page1.xml"/>
</Relationships>"""

    files["visio/pages/pages.xml"] = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Pages xmlns="http://schemas.microsoft.com/office/visio/2012/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xml:space="preserve">
  <Page ID="0" NameU="Page-1" Name="ACDE Architecture">
    <PageSheet>
      <Cell N="PageWidth" V="{page_w}"/>
      <Cell N="PageHeight" V="{page_h}"/>
      <Cell N="DrawingSizeType" V="3"/>
      <Cell N="DrawingResizeType" V="1"/>
    </PageSheet>
    <Rel r:id="rId1"/>
  </Page>
</Pages>"""

    files["visio/pages/_rels/page1.xml.rels"] = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image1.png"/>
</Relationships>"""

    files["visio/pages/page1.xml"] = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<PageContents xmlns="http://schemas.microsoft.com/office/visio/2012/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xml:space="preserve">
  <Shapes>
    <Shape ID="1" Type="Foreign" LineStyle="0" FillStyle="0" TextStyle="0">
      <Cell N="PinX" V="{pin_x}"/>
      <Cell N="PinY" V="{pin_y}"/>
      <Cell N="Width" V="{w_in:.2f}"/>
      <Cell N="Height" V="{h_in:.2f}"/>
      <Cell N="LocPinX" V="{loc_pin_x}" F="Width*0.5"/>
      <Cell N="LocPinY" V="{loc_pin_y}" F="Height*0.5"/>
      <Cell N="Angle" V="0"/>
      <Cell N="FlipX" V="0"/>
      <Cell N="FlipY" V="0"/>
      <Cell N="ResizeMode" V="0"/>
      <ForeignData ForeignType="Bitmap" CompressionType="PNG" r:id="rId1"/>
    </Shape>
  </Shapes>
</PageContents>"""

    os.makedirs(os.path.dirname(out_vsdx) or ".", exist_ok=True)
    with zipfile.ZipFile(out_vsdx, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for fname, content in files.items():
            zout.writestr(fname, content.encode("utf-8"))
        zout.writestr("visio/media/image1.png", png_bytes)
        
    print(f"Native Visio file successfully created at: {out_vsdx} ({os.path.getsize(out_vsdx)} bytes)")

if __name__ == "__main__":
    generate_vsdx()
