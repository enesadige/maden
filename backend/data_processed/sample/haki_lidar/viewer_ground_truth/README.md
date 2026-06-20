# Ground Truth Road Visibility Layers

Bu klasor, `systems_tunnel_ground_truth-master` referanslari dikkate alinarak uretilen yol gorunurlugu katmanlarini icerir.

Onceki `viewer/` klasoru otomatik grid/segment graph uzerinden uretilmis prototip overlay'dir. Yolun daha net gorunmesi icin asil kullanilmasi gereken klasor burasidir.

## Temel Fark

`systems_tunnel_ground_truth-master/network/data/ex_edgelist.csv` gercek EX course topolojisini verir, fakat node koordinatlari yoktur. Bu nedenle bu graph dogrudan 3D LiDAR uzerine cizilmemelidir.

Bu klasordeki yaklasim:

```text
1. EX topology -> rota mantigi ve chokepoint bilgisi
2. EX artifact YAML -> dogru frame ve referans marker bilgisi
3. LiDAR PLY -> gercek zemin/yol benzeri noktalarin secilmesi
```

Yani 3D'de gorunen yol katmani sentetik cizgi degil, LiDAR icinden secilmis gercek zemin/yol noktalaridir.

## Dosyalar

```text
walkable_floor_highlight.ply
```

Point cloud icinden secilen zemin/yol benzeri noktalar. Three.js viewer'da ana PLY ustune parlak turuncu/sari layer olarak bindir.

```text
artifact_markers.ply
```

Ground truth artifact noktalarinin local shifted frame'e cevrilmis marker PLY dosyasi.

```text
ground_truth_artifacts_local.json
```

Artifact noktalarinin hem EX frame hem de PLY ile uyumlu local shifted koordinatlari.

```text
ex_topology_graph.json
```

DARPA EX course topoloji graph'i. Node koordinati yoktur; route logic icin kullan, 3D uzerine direkt cizme.

```text
floor_density_topdown.svg
```

Yol/zemin gorunurlugunu kusbakisi kontrol etmek icin tarayicida acilabilir SVG harita.

```text
road_visibility_layers.json
```

Frontend tarafinda hangi layer'larin nasil yuklenecegini anlatan config dosyasi.

## Frontend Onerisi

Ilk deneme icin bu sirayla yukle:

```text
../pointcloud/tunnel_downsampled.ply
walkable_floor_highlight.ply
artifact_markers.ply
```

Onerilen point size:

```text
tunnel_downsampled.ply        0.018 - 0.03
walkable_floor_highlight.ply  0.07 - 0.10
artifact_markers.ply          0.10 - 0.14
```

## Uretim Komutu

```text
py -3 D:\MadenGuardAI\pipelines\generate_ground_truth_road_visibility.py
```
