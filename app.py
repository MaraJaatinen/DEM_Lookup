import math
import io
import base64
import requests
import numpy as np
import rasterio
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import streamlit as st
import folium
import branca.colormap as bcm
from folium.raster_layers import ImageOverlay
from streamlit_folium import st_folium
from rasterio.io import MemoryFile
from streamlit_cookies_manager import EncryptedCookieManager

st.set_page_config(page_title="Elevation Lookup", page_icon="🏔️", layout="centered")

# ── Cookie manager (encrypts the key at rest in the browser) ──────────────────
cookies = EncryptedCookieManager(
    prefix="elevation_lookup_",
    password=st.secrets["COOKIE_PASSWORD"],
)
if not cookies.ready():
    st.stop()

col_title, col_feedback = st.columns([4, 1])
with col_title:
    st.title("🏔️ Elevation Lookup")
    st.caption("Mean elevation within a circular area — powered by OpenTopography")
with col_feedback:
    st.markdown(
        "<div style='padding-top:1.6rem'><a href='https://forms.gle/uKST4SJR3Q85o1Y18' target='_blank'>Leave feedback</a></div>",
        unsafe_allow_html=True,
    )

# ── Inputs ────────────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)
with col1:
    lat = st.number_input("Latitude", value=60.1699, format="%.6f")
with col2:
    lon = st.number_input("Longitude", value=24.9384, format="%.6f")
st.caption("WGS84 — decimal degrees (e.g. 60.1699, not 60° 10′ 11″)")

radius_km = st.slider("Radius (km)", min_value=1, max_value=50, value=10)
st.caption(f"Diameter: {radius_km * 2} km · Area: {math.pi * radius_km**2:.0f} km²")

col3, col4 = st.columns(2)
with col3:
    dem_type = st.selectbox(
        "DEM source",
        options=["COP30", "SRTMGL1", "SRTMGL3", "AW3D30"],
        format_func=lambda x: {
            "COP30":   "Copernicus GLO-30 (30 m)",
            "SRTMGL1": "SRTMGL1 (30 m)",
            "SRTMGL3": "SRTMGL3 (90 m)",
            "AW3D30":  "AW3D30 (30 m)",
        }[x],
    )
with col4:
    # Pre-fill from cookie if available
    saved_key = cookies.get("api_key", "")
    api_key = st.text_input(
        "OpenTopography API key",
        value=saved_key,
        type="password",
        help="Your key is saved in your browser for next time.",
    )
    # Save to cookie whenever the field has a value
    if api_key and api_key != saved_key:
        cookies["api_key"] = api_key
        cookies.save()


# ── Core fetch ────────────────────────────────────────────────────────────────
def fetch_elevation(lat, lon, radius_km, dem_type, api_key):
    km_per_deg_lat = 111.32
    km_per_deg_lon = 111.32 * math.cos(math.radians(lat))

    d_lat = radius_km / km_per_deg_lat
    d_lon = radius_km / km_per_deg_lon

    south = lat - d_lat
    north = lat + d_lat
    west  = lon - d_lon
    east  = lon + d_lon

    params = {
        "demtype":      dem_type,
        "south":        south,
        "north":        north,
        "west":         west,
        "east":         east,
        "outputFormat": "GTiff",
        "API_Key":      api_key,
    }

    r = requests.get(
        "https://portal.opentopography.org/API/globaldem",
        params=params,
        timeout=60,
    )
    r.raise_for_status()

    with MemoryFile(r.content) as mem:
        with mem.open() as ds:
            data      = ds.read(1).astype(float)
            nodata    = ds.nodata
            transform = ds.transform
            rows, cols = data.shape

    px_lat_km = abs(transform.e) * km_per_deg_lat
    px_lon_km = abs(transform.a) * km_per_deg_lon

    rg, cg = np.mgrid[0:rows, 0:cols]
    dist_km = np.sqrt(
        ((rg - rows / 2) * px_lat_km) ** 2 +
        ((cg - cols / 2) * px_lon_km) ** 2
    )

    mask = dist_km <= radius_km
    if nodata is not None:
        mask &= data != nodata

    valid = data[mask]
    if valid.size == 0:
        raise ValueError("No valid elevation pixels found.")

    return {
        "mean":   round(float(np.mean(valid)), 2),
        "min":    round(float(np.min(valid)),  2),
        "max":    round(float(np.max(valid)),  2),
        "std":    round(float(np.std(valid)),  2),
        "pixels": int(valid.size),
        "data":   data,
        "mask":   mask,
        "bounds": (south, west, north, east),
    }


# ── Raster → RGBA PNG ─────────────────────────────────────────────────────────
def make_overlay_image(data, mask, vmin, vmax):
    cmap = plt.get_cmap("terrain")
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
    rgba = cmap(norm(data))
    rgba[..., 3] = np.where(mask, 0.80, 0.0)

    buf = io.BytesIO()
    plt.imsave(buf, rgba, format="png")
    buf.seek(0)
    return buf.getvalue()


# ── Build Folium map ──────────────────────────────────────────────────────────
def build_map(lat, lon, radius_km, res):
    south, west, north, east = res["bounds"]

    zoom = max(7, min(13, round(13 - math.log2(max(radius_km, 1)))))

    m = folium.Map(
        location=[lat, lon],
        zoom_start=zoom,
        tiles="https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
        attr="© OpenTopoMap (CC-BY-SA) | © OpenStreetMap contributors",
    )

    img_bytes = make_overlay_image(res["data"], res["mask"], res["min"], res["max"])
    img_b64   = base64.b64encode(img_bytes).decode()
    ImageOverlay(
        image=f"data:image/png;base64,{img_b64}",
        bounds=[[south, west], [north, east]],
        opacity=1.0,
        interactive=False,
    ).add_to(m)

    folium.Circle(
        location=[lat, lon],
        radius=radius_km * 1000,
        color="#ffffff",
        weight=1.5,
        fill=False,
        dash_array="6",
    ).add_to(m)

    folium.CircleMarker(
        location=[lat, lon],
        radius=5,
        color="#ffffff",
        weight=2,
        fill=True,
        fill_color="#e74c3c",
        fill_opacity=1.0,
        tooltip=f"{lat}, {lon}",
    ).add_to(m)

    cmap   = plt.get_cmap("terrain")
    colors = [mcolors.to_hex(cmap(p)) for p in np.linspace(0, 1, 10)]
    bcm.LinearColormap(
        colors=colors,
        vmin=res["min"],
        vmax=res["max"],
        caption="Elevation (m asl)",
    ).add_to(m)

    return m


# ── Run ───────────────────────────────────────────────────────────────────────
if st.button("Fetch elevation", type="primary", use_container_width=True):
    if not api_key:
        st.error("Please enter your OpenTopography API key.")
    else:
        with st.spinner("Fetching DEM data…"):
            try:
                res = fetch_elevation(lat, lon, radius_km, dem_type, api_key)

                st.success("Done!")
                st.metric("Mean elevation", f"{res['mean']} m")

                c1, c2, c3 = st.columns(3)
                c1.metric("Min",     f"{res['min']} m")
                c2.metric("Max",     f"{res['max']} m")
                c3.metric("Std dev", f"{res['std']} m")

                st.caption(f"{res['pixels']:,} pixels sampled · {dem_type}")

                st.divider()

                m = build_map(lat, lon, radius_km, res)
                st_folium(m, use_container_width=True, height=500, returned_objects=[])

            except requests.HTTPError as e:
                st.error(f"API error {e.response.status_code} — check your key and coordinates.")
            except Exception as e:
                st.error(f"Something went wrong: {e}")
