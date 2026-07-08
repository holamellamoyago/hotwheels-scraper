# 🏎️ Hot Wheels Scraper → Supabase

Scraper automático del wiki de Hot Wheels usando la **Fandom API** que alimenta una base de datos en Supabase. Tu app Flutter consume los datos sin tener que scrapear nada.

## 🏗️ Arquitectura

```
Fandom API ──▶ GitHub Actions (scraper Python) ──▶ Supabase (PostgreSQL) ◀── Flutter app
   ↑                    (requests + bs4)               (REST API)          (supabase_flutter)
   │                  ┌─────────────┐
   │                  │ Diario:      │  año actual    → ~1 min
   │                  │ Quincenal:   │  1968→actual   → ~9 min
   │                  └─────────────┘
  api.php?action=parse   2000 min gratis/mes
  (sin Cloudflare)       Consumo: ~48 min/mes (2.4%)
```

## 🚀 Setup paso a paso

### 1. Crear proyecto en Supabase

1. Ve a [supabase.com](https://supabase.com) y crea una cuenta gratis
2. Crea un nuevo proyecto (elige una región cercana, ej: `Frankfurt`)
3. Ve al **SQL Editor** y pega el contenido de `migrations/001_create_cars_table.sql`
4. Ejecútalo — crea la tabla `cars`, índices, y permisos RLS

### 2. Obtener las keys de Supabase

Ve a **Project Settings → API** y copia:

| Variable | Valor |
|----------|-------|
| `SUPABASE_URL` | `https://xxx.supabase.co` (Project URL) |
| `SUPABASE_ANON_KEY` | Anon public key (para Flutter) |
| `SUPABASE_SERVICE_KEY` | Service role key (para el scraper) |

> ⚠️ La `SERVICE_KEY` tiene permisos totales. **Nunca la pongas en el cliente Flutter**. Solo se usa desde GitHub Actions.

### 3. Configurar secrets en GitHub

En tu repo → **Settings → Secrets and variables → Actions → Repository secrets**:

| Secret | Valor |
|--------|-------|
| `SUPABASE_URL` | `https://xxx.supabase.co` |
| `SUPABASE_SERVICE_KEY` | `eyJ...` (service_role key) |

### 4. ¡Y ya está!

Los workflows se ejecutan automáticamente:

| Workflow | Cuándo | Qué scrapea | Duración |
|----------|--------|-------------|----------|
| `scrape-daily.yml` | Cada día 06:00 UTC | Año actual | ~1 min |
| `scrape-full.yml` | Días 1 y 15 del mes | 1968→actual | ~9 min |

También puedes ejecutarlos manualmente desde **Actions** → workflow → **Run workflow**.

---

## 📡 Consumir desde Flutter

Añade `supabase_flutter` a tu `pubspec.yaml`:

```yaml
dependencies:
  supabase_flutter: ^2.0.0
```

Inicializa Supabase:

```dart
import 'package:supabase_flutter/supabase_flutter.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  await Supabase.initialize(
    url: 'https://xxx.supabase.co',    // ← tu Project URL
    anonKey: 'eyJ...',                  // ← tu Anon Key (pública)
  );

  runApp(MyApp());
}
```

### Ejemplos de consultas

```dart
final supabase = Supabase.instance.client;

// Todos los coches de un año
final cars2024 = await supabase
    .from('cars').select().eq('year', 2024).order('toy_num');

// Buscar por modelo (búsqueda parcial)
final results = await supabase
    .from('cars').select().ilike('model_name', '%mustang%')
    .order('year', ascending: false);

// Coches de una serie concreta
final treasureHunts = await supabase
    .from('cars').select().ilike('series', '%Treasure Hunt%').eq('year', 2024);

// Últimos añadidos
final latest = await supabase
    .from('cars').select().order('created_at', ascending: false).limit(10);

// Contar total
final count = await supabase.from('cars').count();

// Paginación (50 por página)
final page1 = await supabase
    .from('cars').select().eq('year', 2024).range(0, 49);
```

### Widget de ejemplo

```dart
class CarListPage extends StatefulWidget {
  final int year;
  const CarListPage({super.key, required this.year});

  @override
  State<CarListPage> createState() => _CarListPageState();
}

class _CarListPageState extends State<CarListPage> {
  List<Map<String, dynamic>>? _cars;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadCars();
  }

  Future<void> _loadCars() async {
    final data = await Supabase.instance.client
        .from('cars').select().eq('year', widget.year).order('toy_num');
    setState(() { _cars = data; _loading = false; });
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());

    return ListView.builder(
      itemCount: _cars!.length,
      itemBuilder: (context, index) {
        final car = _cars![index];
        return ListTile(
          leading: car['image_url'] != null
              ? Image.network(car['image_url'], width: 50, fit: BoxFit.cover)
              : const Icon(Icons.directions_car),
          title: Text(car['model_name'] ?? 'Unknown'),
          subtitle: Text(car['series'] ?? ''),
          trailing: Text('#${car['toy_num'] ?? ''}'),
        );
      },
    );
  }
}
```

---

## 🧪 Probar localmente

```bash
pip install -r requirements.txt

# Dry run (sin subir a Supabase)
python -m src.main --all --dry-run

# Subir de verdad
python -m src.main --all

# Solo un año
python -m src.main --years 2025
```

---

## 📁 Estructura del proyecto

```
hotwheels-scraper/
├── .github/workflows/
│   ├── scrape-daily.yml       # Diario (año actual)
│   └── scrape-full.yml        # Quincenal (todos los años)
├── migrations/
│   └── 001_create_cars_table.sql
├── src/
│   ├── __init__.py
│   ├── main.py                # CLI entry point
│   ├── models.py              # HotWheelsCar dataclass
│   ├── scraper.py             # Fandom API + BeautifulSoup
│   └── supabase_client.py     # Cliente Supabase REST
├── requirements.txt
└── README.md
```

---

## 🔄 Plan de ejecución

| Frecuencia | Min/mes | % free tier | Propósito |
|-----------|---------|:-----------:|-----------|
| Diaria (año actual) | ~30 min | 1.5% | Nuevos lanzamientos |
| Quincenal (todo) | ~18 min | 0.9% | Correcciones históricas |
| **Total** | **~48 min** | **2.4%** | |

---

## 📝 Notas

- Las imágenes se guardan como URLs, no se almacenan localmente
- Se usa la **Fandom API** (`api.php?action=parse`) en lugar de scrapeo HTML directo para evitar bloqueos de Cloudflare
- Los datos históricos apenas cambian, por eso solo se rescrapean quincenalmente
- La tabla `cars` tiene constraint `UNIQUE(year, toy_num, model_name)` para evitar duplicados
- RLS (Row Level Security): lectura anónima permitida, escritura solo con service key
