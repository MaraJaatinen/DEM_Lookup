# 🏔️ Elevation Lookup

A lightweight web tool to fetch mean elevation for a circular area anywhere on Earth. Enter coordinates, set a radius, and get elevation statistics with a colorized terrain overlay on an interactive map — no GIS software needed.

Built with Streamlit and the [OpenTopography](https://portal.opentopography.org) API.

---

## What it does

- Fetches a DEM (Digital Elevation Model) raster from OpenTopography for a bounding box around your coordinates
- Applies a circular mask to the raster so only pixels within your chosen radius are included
- Returns mean, min, max, and standard deviation of elevation in metres
- Displays the colorized raster overlaid on OpenTopoMap tiles for visual verification

---

## Running locally

**1. Install dependencies**

```bash
pip install streamlit requests rasterio numpy matplotlib folium streamlit-folium
```

**2. Get an API key**

Register for a free account at [portal.opentopography.org/myopentopo](https://portal.opentopography.org/myopentopo) to get your API key.

**3. Run**

```bash
streamlit run app.py
```

---

## Deploying to Streamlit Community Cloud

1. Push `app.py` and `requirements.txt` to a GitHub repository
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub
3. Point it at your repo and select `app.py` as the main file
4. Deploy — you'll get a public URL at `yourname.streamlit.app`

Each user enters their own OpenTopography API key in the app. If you want to bake in a key for private use, see [Streamlit Secrets Management](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management).

---

## Inputs

| Field | Description |
|---|---|
| Latitude / Longitude | WGS84 decimal degrees (e.g. `60.1699`, not `60° 10′ 11″`) |
| Radius | 1–50 km. The sampled area is a circle of this radius (diameter = 2×) |
| DEM source | See table below |
| API key | Your OpenTopography API key |

### DEM sources

| Option | Resolution | Notes |
|---|---|---|
| Copernicus GLO-30 | 30 m | Default. Good global coverage, recent data |
| SRTMGL1 | 30 m | NASA SRTM, collected 2000. Solid global baseline |
| SRTMGL3 | 90 m | Same as SRTMGL1 but lower resolution — faster for large areas |
| AW3D30 | 30 m | ALOS/JAXA dataset, strong coverage in Asia and mountainous terrain |

---

## Output

**Statistics**

- Mean elevation (metres above sea level)
- Min / Max / Standard deviation

**Map**

- OpenTopoMap basemap (contour lines, hillshading, terrain labels)
- Your elevation raster overlaid in the `terrain` colormap at 80% opacity
- Dashed white circle marking the boundary
- Red dot at the centre point
- Colorbar legend in the corner

---

## Dependencies

| Package | Purpose |
|---|---|
| `streamlit` | Web UI |
| `requests` | OpenTopography API calls |
| `rasterio` | Reading GeoTIFF raster data |
| `numpy` | Circular masking and statistics |
| `matplotlib` | Colorizing the raster |
| `folium` + `streamlit-folium` | Interactive map and overlay |

---

## Feedback

Found a bug or have a suggestion? [Leave feedback here](https://forms.gle/uKST4SJR3Q85o1Y18).
