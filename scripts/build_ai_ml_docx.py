from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape


OUT = Path("/Users/enesdasci/Desktop/MadenGuard_AI_ML_Kullanim_Rehberi.docx")


def xml_text(value: str) -> str:
    return escape(value, {'"': "&quot;"})


def run(text: str, bold: bool = False, color: str | None = None) -> str:
    props = []
    if bold:
        props.append("<w:b/>")
    if color:
        props.append(f'<w:color w:val="{color}"/>')
    props_xml = f"<w:rPr>{''.join(props)}</w:rPr>" if props else ""
    return f"<w:r>{props_xml}<w:t xml:space=\"preserve\">{xml_text(text)}</w:t></w:r>"


def paragraph(
    text: str = "",
    style: str = "Normal",
    *,
    bold_prefix: str | None = None,
    num_id: int | None = None,
    level: int = 0,
    color: str | None = None,
) -> str:
    p_pr = [f'<w:pStyle w:val="{style}"/>']
    if num_id is not None:
        p_pr.append(
            f"<w:numPr><w:ilvl w:val=\"{level}\"/><w:numId w:val=\"{num_id}\"/></w:numPr>"
        )
    if style.startswith("Heading"):
        p_pr.append("<w:keepNext/>")
    body = ""
    if bold_prefix and text.startswith(bold_prefix):
        body = run(bold_prefix, bold=True, color=color) + run(text[len(bold_prefix) :], color=color)
    else:
        body = run(text, color=color)
    return f"<w:p><w:pPr>{''.join(p_pr)}</w:pPr>{body}</w:p>"


def bullet(text: str, level: int = 0) -> str:
    return paragraph(text, num_id=1, level=level)


def numbered(text: str, level: int = 0) -> str:
    return paragraph(text, num_id=2, level=level)


def note(text: str) -> str:
    return paragraph(text, style="Callout")


def section(title: str) -> str:
    return paragraph(title, style="Heading1")


def subsection(title: str) -> str:
    return paragraph(title, style="Heading2")


def mini(title: str) -> str:
    return paragraph(title, style="Heading3")


def table(rows: list[list[str]], widths: list[int]) -> str:
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)
    out = [
        '<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/>'
        '<w:tblW w:w="9360" w:type="dxa"/>'
        '<w:tblInd w:w="120" w:type="dxa"/>'
        '<w:tblLook w:firstRow="1" w:lastRow="0" w:firstColumn="0" w:lastColumn="0" '
        'w:noHBand="0" w:noVBand="1"/></w:tblPr>',
        f"<w:tblGrid>{grid}</w:tblGrid>",
    ]
    for ridx, row in enumerate(rows):
        out.append("<w:tr>")
        for cidx, cell in enumerate(row):
            fill = '<w:shd w:fill="E8EEF5"/>' if ridx == 0 else ""
            bold = ridx == 0
            out.append(
                f"<w:tc><w:tcPr><w:tcW w:w=\"{widths[cidx]}\" w:type=\"dxa\"/>"
                f"{fill}<w:tcMar><w:top w:w=\"80\" w:type=\"dxa\"/>"
                '<w:left w:w="120" w:type="dxa"/><w:bottom w:w="80" w:type="dxa"/>'
                '<w:right w:w="120" w:type="dxa"/></w:tcMar></w:tcPr>'
                f"{paragraph(cell, bold_prefix=cell if bold else None)}</w:tc>"
            )
        out.append("</w:tr>")
    out.append("</w:tbl>")
    return "".join(out)


def build_body() -> list[str]:
    body: list[str] = []
    body.append(paragraph("MadenGuard AI", style="Title"))
    body.append(paragraph("Ekip Bazlı Yapay Zeka ve ML Kullanım Rehberi", style="Subtitle"))
    body.append(
        paragraph(
            "Amaç: Her ekip üyesinin kendi modülünde yapay zeka, makine öğrenmesi veya "
            "açıklanabilir algoritmik karar desteğini nerede kullanacağını netleştirmek. "
            "Bu doküman MVP için gerçekçi, uygulanabilir ve rapor diliyle uyumlu bir yol haritasıdır."
        )
    )
    body.append(note("Kısa karar: Yapay zeka bu projede ayrı bir süs modülü değil; LiDAR, gaz/metan, UWB worker ve graph verilerini birleştirerek segment bazlı açıklanabilir risk skoru üreten karar motorudur."))

    body.append(section("1. Genel AI/ML Mantığı"))
    body.append(
        paragraph(
            "MadenGuard AI'da AI/ML dört katmanda kullanılır: anomali tespiti, risk skorlama, "
            "konum güvenilirliği ve karar/risk füzyonu. MVP'de derin öğrenme şart değildir; "
            "kural tabanlı skorlar, istatistiksel anomali tespiti ve klasik ML yöntemleri yeterlidir."
        )
    )
    for item in [
        "MVP seviyesi: threshold, z-score, rolling mean, yoğunluk/bağlantı metriği ve Dijkstra/A* gibi açıklanabilir yöntemler.",
        "ML seviyesi: Isolation Forest, basit sınıflandırıcılar veya anomali modelleri ile risk skorunu güçlendirme.",
        "Sunum dili: Sistem tek veri kaynağına bakmaz; LiDAR + gaz + worker + graph verisini birlikte değerlendirir.",
        "Ana çıktı: Her segment için final_risk_score, risk_level ve active_reasons üretmek.",
    ]:
        body.append(bullet(item))

    body.append(
        table(
            [
                ["Kişi", "Modül", "AI/ML nerede?", "Ana çıktı"],
                ["Haki", "LiDAR / dijital ikiz", "Segment feature çıkarımı ve geometri anomali/risk skoru", "geometry_risk.json"],
                ["Recep", "Gaz / metan", "Zaman serisi anomali tespiti ve sensör güvenilirliği", "environmental_risk.json"],
                ["Hüseyin", "UWB / worker", "Konum-segment eşleme, LOS/NLOS güvenilirlik ve exposure risk", "worker_exposure_risk.json"],
                ["Enes", "Backend / fusion", "Hibrit risk füzyonu, rota karar motoru ve açıklanabilir risk nedeni", "risk_scores.json + API"],
                ["Selim", "Frontend", "AI hesaplamaz; AI sonuçlarını anlaşılır görselleştirir", "dashboard"],
            ],
            [1260, 1800, 3900, 2400],
        )
    )

    body.append(section("2. Haki - LiDAR / Dijital İkiz Geometri"))
    body.append(
        paragraph(
            "Haki'nin AI/ML katkısı ham nokta bulutunu doğrudan modele sokmak değil, LiDAR'dan segment bazlı anlamlı özellikler çıkarmaktır. "
            "Bu özellikler backend risk motoruna geometri riski olarak girer."
        )
    )
    body.append(mini("Kullanılacak özellikler"))
    for item in [
        "Segment genişliği, uzunluğu, yükseklik aralığı ve tavan/taban farkı.",
        "Nokta yoğunluğu, lokal seyrekleşme, kopukluk ve gürültü göstergeleri.",
        "Tavan pürüzlülüğü, yüzey düzensizliği ve dar geçit metriği.",
        "Segment bağlantı sayısı: tek bağlantılı veya kaçışa kritik segmentler daha riskli kabul edilir.",
    ]:
        body.append(bullet(item))
    body.append(mini("MVP yöntemi"))
    for item in [
        "LAS dosyasını chunk tabanlı okuyup 500k-1M civarında PLY üretmek.",
        "X-Y düzleminde segment çıkarmak, Z eksenini yükseklik ve risk metriği için kullanmak.",
        "Her segment için geometry_risk değerini 0-100 arasında hesaplamak.",
        "Risk nedenini açıklamak: dar geçit, düşük yoğunluk, tek rota bağımlılığı, tavan düzensizliği gibi.",
    ]:
        body.append(bullet(item))
    body.append(mini("ML eklenebilecek yer"))
    for item in [
        "Segment feature tablosu üzerinde Isolation Forest veya benzeri unsupervised anomaly detection kullanılabilir.",
        "Normal segmentlerden sapan geometrik bölgeler otomatik 'anomalous geometry' olarak işaretlenebilir.",
        "Ancak MVP'de kural tabanlı geometri skoru yeterlidir; ML sonradan skor kalibrasyonu için eklenebilir.",
    ]:
        body.append(bullet(item))
    body.append(mini("Teslim beklentisi"))
    for item in [
        "pointcloud/tunnel_preview_500k.ply ve pointcloud/tunnel_downsampled.ply.",
        "segments/map_segments.json ve segments/segment_metadata.json.",
        "graph/mine_graph.json.",
        "risk/geometry_risk.json; her kayıtta segment_id, geometry_risk, risk_level ve risk_reason olmalı.",
    ]:
        body.append(bullet(item))

    body.append(section("3. Recep - Metan / Gaz Sensör Risk Analizi"))
    body.append(
        paragraph(
            "Gaz verisi Recep tarafında işlenecek. Bu modülün AI/ML katkısı, metan/gaz zaman serilerinde normal davranıştan sapmayı bulmak ve segment bazlı environmental risk üretmektir."
        )
    )
    body.append(mini("Kullanılacak veri"))
    for item in [
        "Ana veri: Mendeley Methane Coal Mine veri seti.",
        "Destek veri: UCI Gas Sensor Drift; sensör drift/güvenilirlik fikrini göstermek için kullanılabilir.",
        "Öncelikli kolonlar: MM263, MM264, MM256; bağlam için sıcaklık, nem ve basınç kolonları.",
    ]:
        body.append(bullet(item))
    body.append(mini("MVP yöntemi"))
    for item in [
        "Threshold: belirlenen eşik üstündeki metan değeri riskli sayılır.",
        "Z-score: değerin normal dağılımdan ne kadar saptığı hesaplanır.",
        "Rolling mean: kısa vadeli ani artışlar yakalanır.",
        "Anomaly score: threshold + z-score + rolling değişimden 0-1 veya 0-100 skor üretilir.",
    ]:
        body.append(bullet(item))
    body.append(mini("ML eklenebilecek yer"))
    for item in [
        "Isolation Forest ile çok değişkenli gaz/anomali skoru üretilebilir.",
        "Sensör drift için UCI verisinden confidence/reliability skoru çıkarılabilir.",
        "Bu confidence değeri backend risk fusion'da çevresel riskin ağırlığını artırıp azaltmak için kullanılabilir.",
    ]:
        body.append(bullet(item))
    body.append(mini("Teslim beklentisi"))
    for item in [
        "sensors/methane_clean_sample.csv.",
        "sensors/environmental_anomaly_scores.csv.",
        "risk/environmental_risk.json.",
        "environmental_risk.json içinde segment_id, sensor_id, time_step veya timestamp, methane_value, anomaly_score, environmental_risk, risk_score, risk_level ve reason olmalı.",
    ]:
        body.append(bullet(item))

    body.append(section("4. Hüseyin - UWB / Worker Tracking"))
    body.append(
        paragraph(
            "Hüseyin'in AI/ML katkısı işçi konumunu sadece koordinat olarak vermek değil; bu konumu Haki'nin segmentlerine bağlamak, konum güvenilirliğini hesaplamak ve işçi risk maruziyetini üretmektir."
        )
    )
    body.append(mini("MVP yöntemi"))
    for item in [
        "UTIL UWB pose_x, pose_y, pose_z verileri temizlenir ve tünel koordinat sistemine ölçeklenir.",
        "Her worker konumu en yakın segment merkezine veya segment sınırına göre current_segment alanına bağlanır.",
        "Riskli segmentte worker varsa worker_exposure_risk yükseltilir.",
        "İşçi çıkış yolu kapanmış bölgede kalıyorsa status 'trapped' veya 'critical' olur.",
    ]:
        body.append(bullet(item))
    body.append(mini("ML eklenebilecek yer"))
    for item in [
        "LOS/NLOS ayrımı için sinyal kalitesi özelliklerinden basit classifier üretilebilir.",
        "position_reliability değeri LOS/NLOS, sinyal kalitesi ve hareket sürekliliğine göre hesaplanabilir.",
        "Uzun süre hareketsiz kalma, beklenmeyen rota sapması veya riskli segmente yaklaşma gibi davranış anomalileri çıkarılabilir.",
    ]:
        body.append(bullet(item))
    body.append(mini("Sınır"))
    for item in [
        "Hüseyin ayrı bir maden segment haritası üretmemeli; Haki'nin map_segments.json dosyasındaki segment_id değerlerini kullanmalı.",
        "2D map, frontend veya backend router ana teslim değil; core teslim worker JSON ve exposure risk olmalı.",
    ]:
        body.append(bullet(item))
    body.append(mini("Teslim beklentisi"))
    for item in [
        "workers/worker_positions_clean.csv.",
        "workers/worker_positions_demo.json.",
        "workers/worker_segment_timeline.json.",
        "risk/worker_exposure_risk.json.",
        "Her worker kaydında worker_id, time_step/timestamp, position, current_segment, position_reliability ve status olmalı.",
    ]:
        body.append(bullet(item))

    body.append(section("5. Enes - Backend / Hibrit Risk Fusion ve Rota Motoru"))
    body.append(
        paragraph(
            "Backend projenin karar merkezidir. AI/ML sonuçlarının birleştiği, final risk skorunun üretildiği ve acil rota kararının verildiği yer Enes'in backend katmanıdır."
        )
    )
    body.append(mini("Backend'in AI görevi"))
    for item in [
        "Haki'den geometry_risk, Recep'ten environmental_risk, Hüseyin'den worker_exposure_risk alınır.",
        "Her segment için final_risk_score hesaplanır.",
        "Risk level low, medium, high, critical olarak atanır.",
        "Her risk için active_reasons üretilir; frontend ve rapor bu nedenleri gösterir.",
    ]:
        body.append(bullet(item))
    body.append(mini("MVP risk formülü"))
    body.append(
        note(
            "Örnek: final_risk = 0.30 * environmental_risk + 0.25 * geometry_risk + "
            "0.25 * worker_exposure_risk + 0.20 * route_blockage_risk"
        )
    )
    for item in [
        "Ağırlıklar MVP'de elle belirlenebilir; daha sonra veri geldikçe kalibre edilebilir.",
        "Risk motoru açıklanabilir olmalı: sadece skor değil, neden listesi dönmeli.",
        "Django veya FastAPI fark etmez; önemli olan data loader, risk engine, route engine ve API kontratının sabit olmasıdır.",
    ]:
        body.append(bullet(item))
    body.append(mini("ML eklenebilecek yer"))
    for item in [
        "Risk ağırlıkları ileride küçük doğrulama setiyle kalibre edilebilir.",
        "Segment geçmişi oluşursa trend tabanlı risk tahmini yapılabilir.",
        "Şu an için backend'deki en güçlü AI iddiası açıklanabilir hibrit risk fusion motorudur.",
    ]:
        body.append(bullet(item))
    body.append(mini("Acil rota"))
    for item in [
        "mine_graph.json üzerinden Dijkstra veya A* ile rota hesaplanır.",
        "Kapanmış segmentler graf dışına alınır veya sonsuz maliyet verilir.",
        "Sadece en kısa yol değil, risk cezası düşük en güvenli yol hesaplanır.",
        "Yol yoksa worker_trapped sonucu döner.",
    ]:
        body.append(bullet(item))
    body.append(mini("Teslim/API beklentisi"))
    for item in [
        "GET /api/health.",
        "GET /api/digital-twin/segments ve /api/digital-twin/graph.",
        "GET /api/workers.",
        "GET /api/risk/segments.",
        "GET /api/gas-sensors.",
        "GET /api/scenarios/collapse.",
        "GET /api/routes/emergency.",
    ]:
        body.append(bullet(item))

    body.append(section("6. Selim - Frontend / AI Sonuçlarını Gösterme"))
    body.append(
        paragraph(
            "Frontend tarafında AI/ML hesaplaması yapılmamalı. Selim'in görevi backend'in ürettiği AI/risk kararını açık ve anlaşılır göstermek olmalı."
        )
    )
    body.append(mini("Frontend'de gösterilecek AI çıktıları"))
    for item in [
        "Segment risk rengi: low yeşil, medium sarı/turuncu, high/critical kırmızı.",
        "AI Risk Score: final_risk_score değeri.",
        "Risk nedeni: active_reasons listesi.",
        "Worker durumu: safe, caution, at_risk, trapped.",
        "Acil rota: route_segments, estimated_time, reachable veya trapped sonucu.",
    ]:
        body.append(bullet(item))
    body.append(mini("Yapılmayacak"))
    for item in [
        "Frontend ham LAS, büyük CSV veya raw dataset açmayacak.",
        "Frontend final risk hesabını kendi içinde tekrar üretmeyecek.",
        "Frontend sadece mock veriden API'ye geçişi kolaylaştıracak şekilde componentleri koruyacak.",
    ]:
        body.append(bullet(item))

    body.append(section("7. Ortak Veri Standardı"))
    for item in [
        "Ortak anahtar: segment_id.",
        "Önerilen segment ID formatı: S001, S002, S003, S047.",
        "Eski SEG_047 gibi prototip ID'leri backend tarafında S047 formatına normalize edilebilir.",
        "Risk seviyeleri: low, medium, high, critical.",
        "Kapanmış segment: is_blocked = true.",
        "Çıkış segmenti: is_exit = true.",
    ]:
        body.append(bullet(item))
    body.append(mini("Her final risk kaydı için önerilen alanlar"))
    for item in [
        "segment_id",
        "final_risk_score",
        "risk_level",
        "geometry_risk",
        "environmental_risk",
        "worker_exposure_risk",
        "route_blockage_risk",
        "active_reasons",
        "updated_at veya time_step",
    ]:
        body.append(bullet(item))

    body.append(section("8. Demo Akışı"))
    for item in [
        "Normal maden dijital ikizi açılır.",
        "Worker konumları segmentler üzerinde gösterilir.",
        "Gaz/metan anomali senaryosu çalışır.",
        "Backend AI risk engine ilgili segmentin riskini yükseltir.",
        "Göçük senaryosu çalışır; bir segment is_blocked olur.",
        "Rota motoru worker için çıkış yolunu arar.",
        "Yol varsa alternatif rota gösterilir; yoksa mahsur/trapped uyarısı verilir.",
        "Frontend risk nedenlerini ve rota sonucunu panelde gösterir.",
    ]:
        body.append(numbered(item))

    body.append(section("9. Rapor Dilinde Kullanılacak Cümle"))
    body.append(
        note(
            "MadenGuard AI'da yapay zeka, LiDAR geometrisi, metan/gaz sensör anomalileri ve UWB worker konum verisini birleştiren hibrit risk analiz motorunda kullanılır. Sistem segment bazında açıklanabilir risk skoru üretir ve acil durumda graf tabanlı rota algoritmasıyla güvenli kaçış/erişim önerisi sunar."
        )
    )

    body.append(section("10. Kaçınılacak Yanlış İddialar"))
    for item in [
        "Derin öğrenme ile tam otonom kurtarma yapıyoruz denmemeli.",
        "Ham LAS dosyasını frontend'de açıyoruz denmemeli.",
        "UWB verisi gerçek maden ölçeğinde doğrudan hazır kabul edilmemeli; ölçekleme ve segment eşleme gerektiği belirtilmeli.",
        "AI kara kutu karar veriyor denmemeli; açıklanabilir hibrit risk skoru üretiyor denmeli.",
    ]:
        body.append(bullet(item))

    body.append(paragraph(f"Hazırlanma tarihi: {datetime.now().strftime('%Y-%m-%d %H:%M')}", style="FooterText"))
    return body


def styles_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:pPr><w:spacing w:after="120" w:line="300" w:lineRule="auto"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Title">
    <w:name w:val="Title"/>
    <w:pPr><w:spacing w:after="80"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:b/><w:color w:val="0B2545"/><w:sz w:val="48"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Subtitle">
    <w:name w:val="Subtitle"/>
    <w:pPr><w:spacing w:after="320"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:color w:val="555555"/><w:sz w:val="28"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/>
    <w:basedOn w:val="Normal"/>
    <w:next w:val="Normal"/>
    <w:pPr><w:keepNext/><w:spacing w:before="360" w:after="200"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:b/><w:color w:val="2E74B5"/><w:sz w:val="32"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="heading 2"/>
    <w:basedOn w:val="Normal"/>
    <w:next w:val="Normal"/>
    <w:pPr><w:keepNext/><w:spacing w:before="280" w:after="140"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:b/><w:color w:val="2E74B5"/><w:sz w:val="26"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading3">
    <w:name w:val="heading 3"/>
    <w:basedOn w:val="Normal"/>
    <w:next w:val="Normal"/>
    <w:pPr><w:keepNext/><w:spacing w:before="200" w:after="100"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:b/><w:color w:val="1F4D78"/><w:sz w:val="24"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Callout">
    <w:name w:val="Callout"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr>
      <w:spacing w:before="120" w:after="160" w:line="300" w:lineRule="auto"/>
      <w:ind w:left="240" w:right="240"/>
      <w:pBdr><w:left w:val="single" w:sz="12" w:space="8" w:color="2E74B5"/></w:pBdr>
      <w:shd w:fill="F4F6F9"/>
    </w:pPr>
    <w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:color w:val="0B2545"/><w:sz w:val="22"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="FooterText">
    <w:name w:val="Footer Text"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:spacing w:before="240" w:after="0"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:color w:val="666666"/><w:sz w:val="18"/></w:rPr>
  </w:style>
  <w:style w:type="table" w:styleId="TableGrid">
    <w:name w:val="Table Grid"/>
    <w:tblPr>
      <w:tblBorders>
        <w:top w:val="single" w:sz="4" w:space="0" w:color="D0D7DE"/>
        <w:left w:val="single" w:sz="4" w:space="0" w:color="D0D7DE"/>
        <w:bottom w:val="single" w:sz="4" w:space="0" w:color="D0D7DE"/>
        <w:right w:val="single" w:sz="4" w:space="0" w:color="D0D7DE"/>
        <w:insideH w:val="single" w:sz="4" w:space="0" w:color="D0D7DE"/>
        <w:insideV w:val="single" w:sz="4" w:space="0" w:color="D0D7DE"/>
      </w:tblBorders>
    </w:tblPr>
  </w:style>
</w:styles>
"""


def numbering_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:abstractNum w:abstractNumId="1">
    <w:multiLevelType w:val="hybridMultilevel"/>
    <w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="•"/><w:lvlJc w:val="left"/><w:pPr><w:tabs><w:tab w:val="num" w:pos="540"/></w:tabs><w:ind w:left="540" w:hanging="270"/></w:pPr></w:lvl>
    <w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="◦"/><w:lvlJc w:val="left"/><w:pPr><w:tabs><w:tab w:val="num" w:pos="900"/></w:tabs><w:ind w:left="900" w:hanging="270"/></w:pPr></w:lvl>
  </w:abstractNum>
  <w:num w:numId="1"><w:abstractNumId w:val="1"/></w:num>
  <w:abstractNum w:abstractNumId="2">
    <w:multiLevelType w:val="hybridMultilevel"/>
    <w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/><w:lvlJc w:val="left"/><w:pPr><w:tabs><w:tab w:val="num" w:pos="540"/></w:tabs><w:ind w:left="540" w:hanging="270"/></w:pPr></w:lvl>
  </w:abstractNum>
  <w:num w:numId="2"><w:abstractNumId w:val="2"/></w:num>
</w:numbering>
"""


def document_xml() -> str:
    body = "".join(build_body())
    sect = (
        '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
        'w:header="708" w:footer="708" w:gutter="0"/>'
        '<w:cols w:space="720"/><w:docGrid w:linePitch="360"/></w:sectPr>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas" '
        'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
        'xmlns:o="urn:schemas-microsoft-com:office:office" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" '
        'xmlns:v="urn:schemas-microsoft-com:vml" '
        'xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
        'xmlns:w10="urn:schemas-microsoft-com:office:word" '
        'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" '
        'xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup" '
        'xmlns:wpi="http://schemas.microsoft.com/office/word/2010/wordprocessingInk" '
        'xmlns:wne="http://schemas.microsoft.com/office/word/2006/wordml" '
        'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
        'mc:Ignorable="w14 wp14"><w:body>'
        f"{body}{sect}</w:body></w:document>"
    )


def content_types_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
"""


def rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"""


def document_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>
</Relationships>
"""


def core_xml() -> str:
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>MadenGuard AI - Ekip Bazlı Yapay Zeka ve ML Kullanım Rehberi</dc:title>
  <dc:creator>Codex</dc:creator>
  <cp:lastModifiedBy>Codex</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>
</cp:coreProperties>
"""


def app_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Codex</Application>
  <DocSecurity>0</DocSecurity>
  <ScaleCrop>false</ScaleCrop>
  <Company></Company>
  <LinksUpToDate>false</LinksUpToDate>
  <SharedDoc>false</SharedDoc>
  <HyperlinksChanged>false</HyperlinksChanged>
  <AppVersion>16.0000</AppVersion>
</Properties>
"""


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", content_types_xml())
        docx.writestr("_rels/.rels", rels_xml())
        docx.writestr("word/_rels/document.xml.rels", document_rels_xml())
        docx.writestr("word/document.xml", document_xml())
        docx.writestr("word/styles.xml", styles_xml())
        docx.writestr("word/numbering.xml", numbering_xml())
        docx.writestr("docProps/core.xml", core_xml())
        docx.writestr("docProps/app.xml", app_xml())
    print(OUT)


if __name__ == "__main__":
    main()
