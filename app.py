import math
import io
import base64
import requests
import numpy as np
import rasterio
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.colors as mcolors
import streamlit as st
import folium
import branca.colormap as bcm
from folium.raster_layers import ImageOverlay
from streamlit_folium import st_folium
from rasterio.io import MemoryFile
from streamlit_cookies_manager import EncryptedCookieManager

st.set_page_config(page_title="Elevation Lookup", page_icon="🏔️", layout="centered")

# ── Cookie manager ─────────────────────────────────────────────────────────────
cookies = EncryptedCookieManager(
    prefix="elevation_lookup_",
    password=st.secrets["COOKIE_PASSWORD"],
)
if not cookies.ready():
    st.stop()

# ── Terms of use text ─────────────────────────────────────────────────────────
TERMS_TEXT = """
**Elevation Lookup — Terms of Use**

This tool is provided as-is for use by qualified professionals in relevant technical fields.
It is currently in **beta** and under active development.

**No warranty.** Results are provided without any guarantee of accuracy, completeness,
or fitness for purpose. Elevation data is sourced from third-party datasets (OpenTopography /
Copernicus GLO-30) and may contain errors, voids, or artefacts.

**Verify independently.** All outputs — including mean elevation, site elevation, terrain
correction, and rime ice reference height — must be verified using independent methods before
being used in any structural assessment, design, or regulatory submission.

**Professional responsibility.** The user assumes full responsibility for interpreting and
applying results. This tool does not replace engineering judgement or site surveys.

**Not for general use.** This tool is intended for use by people with relevant technical
knowledge and is not suitable for general public use.

By continuing you confirm that you have read, understood, and accepted these terms.
"""

# ── Terms gate — block the app until accepted ─────────────────────────────────
terms_accepted = cookies.get("terms_accepted", "")

@st.dialog("Terms of Use")
def show_terms_gate():
    st.markdown(TERMS_TEXT)
    if st.button("I understand and accept", type="primary", use_container_width=True):
        cookies["terms_accepted"] = "yes"
        cookies.save()
        st.rerun()

if terms_accepted != "yes":
    show_terms_gate()
    st.stop()

# ── Terms popup (re-openable) ─────────────────────────────────────────────────
@st.dialog("Terms of Use")
def show_terms_popup():
    st.markdown(TERMS_TEXT)
    st.button("Close", use_container_width=True)

if st.session_state.get("open_terms"):
    st.session_state["open_terms"] = False
    show_terms_popup()

# ── Header ────────────────────────────────────────────────────────────────────
col_title, col_feedback = st.columns([4, 1])
with col_title:
    st.title("🏔️ Elevation Lookup")
    st.caption("Mean elevation within a circular area — powered by OpenTopography")
with col_feedback:
    st.markdown(
        "<div style='padding-top:1.6rem'><a href='https://forms.gle/uKST4SJR3Q85o1Y18' target='_blank'>Leave feedback</a></div>",
        unsafe_allow_html=True,
    )

# ── Persistent ToS reminder ───────────────────────────────────────────────────
warn_col, link_col = st.columns([5, 1])
with warn_col:
    st.warning(
        "**Beta — verify all results independently before use in any assessment or design.** "
        "For use by qualified professionals only."
    )
with link_col:
    st.markdown("<div style='padding-top:1rem'>", unsafe_allow_html=True)
    if st.button("Terms of use", use_container_width=True):
        st.session_state["open_terms"] = True
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

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
    saved_key = cookies.get("api_key", "")
    api_key = st.text_input(
        "OpenTopography API key",
        value=saved_key,
        type="password",
        help="Your key is saved in your browser for next time.",
    )
    if api_key and api_key != saved_key:
        cookies["api_key"] = api_key
        cookies.save()

st.divider()
st.subheader("Structure")
col5, col6 = st.columns(2)
with col5:
    tower_height = st.number_input("Structure height (m)", min_value=0.0, value=100.0, step=1.0)


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

    centre_elev = float(data[rows // 2, cols // 2])

    valid = data[mask]
    if valid.size == 0:
        raise ValueError("No valid elevation pixels found.")

    return {
        "mean":    round(float(np.mean(valid)), 1),
        "min":     round(float(np.min(valid)),  1),
        "max":     round(float(np.max(valid)),  1),
        "std":     round(float(np.std(valid)),  1),
        "centre":  round(centre_elev,           1),
        "pixels":  int(valid.size),
        "data":    data,
        "mask":    mask,
        "bounds":  (south, west, north, east),
    }


# ── Reference height ──────────────────────────────────────────────────────────
def calc_reference_height(site_elev, mean_elev, tower_height):
    terrain_correction = max(0.0, site_elev - mean_elev)
    ref_height         = terrain_correction + (2 / 3) * tower_height
    assessment_asl     = site_elev + (2 / 3) * tower_height
    return round(ref_height, 1), round(assessment_asl, 1), round(terrain_correction, 1)


# ── Cross-section diagram ─────────────────────────────────────────────────────
def make_diagram(site_elev, mean_elev, tower_height, ref_height, assessment_asl):
    tower_tip_asl = site_elev + tower_height
    assess_point  = site_elev + (2 / 3) * tower_height

    y_min  = min(site_elev, mean_elev) - tower_height * 0.15
    y_max  = tower_tip_asl + tower_height * 0.15
    y_span = y_max - y_min

    fig, ax = plt.subplots(figsize=(6, 5))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    ax.axhspan(y_min, mean_elev, color="#d4e8c2", alpha=0.6, zorder=0)
    ax.axhline(mean_elev,     color="#5a8a3c", linewidth=1.5, linestyle="--", zorder=1)
    ax.axhline(site_elev,     color="#8B6914", linewidth=2,   zorder=2)

    tower_x   = 0.45
    bar_width = 0.06
    ax.add_patch(mpatches.FancyArrow(
        tower_x, site_elev, 0, tower_height - y_span * 0.02,
        width=bar_width, head_width=bar_width * 1.8, head_length=y_span * 0.02,
        color="#555", zorder=3,
    ))

    ax.plot(tower_x, assess_point, "o", color="#c0392b", markersize=8, zorder=5)
    ax.axhline(assess_point, color="#c0392b", linewidth=0.8, linestyle=":", alpha=0.5, zorder=4)

    lx = 0.56
    fs = 8.5

    def label(y, text, value_str, color):
        ax.annotate(
            f"{text}\n{value_str}",
            xy=(tower_x, y), xytext=(lx, y),
            fontsize=fs, color=color, va="center",
            arrowprops=dict(arrowstyle="-", color=color, lw=0.8),
            annotation_clip=False,
        )

    label(tower_tip_asl, "Tower tip",       f"{tower_tip_asl:.1f} m asl",  "#333333")
    label(assess_point,  "Assessment point\n(2/3 height + terrain)",
                                             f"{assessment_asl:.1f} m asl  |  ref {ref_height:.1f} m", "#c0392b")
    label(site_elev,     "Site elevation",  f"{site_elev:.1f} m asl",      "#8B6914")
    label(mean_elev,     "Mean terrain",    f"{mean_elev:.1f} m asl",      "#5a8a3c")

    ax.set_xlim(0, 1)
    ax.set_ylim(y_min, y_max)
    ax.set_ylabel("Elevation (m asl)", fontsize=9)
    ax.set_xticks([])
    ax.spines[["top", "right", "bottom"]].set_visible(False)
    ax.tick_params(axis="y", labelsize=8)

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


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


# ── Folium map ────────────────────────────────────────────────────────────────
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
        opacity=1.0, interactive=False,
    ).add_to(m)

    folium.Circle(
        location=[lat, lon], radius=radius_km * 1000,
        color="#ffffff", weight=1.5, fill=False, dash_array="6",
    ).add_to(m)

    folium.CircleMarker(
        location=[lat, lon], radius=5,
        color="#ffffff", weight=2,
        fill=True, fill_color="#e74c3c", fill_opacity=1.0,
        tooltip=f"{lat}, {lon}",
    ).add_to(m)

    cmap   = plt.get_cmap("terrain")
    colors = [mcolors.to_hex(cmap(p)) for p in np.linspace(0, 1, 10)]
    bcm.LinearColormap(
        colors=colors, vmin=res["min"], vmax=res["max"],
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

                c0, c1, c2, c3, c4 = st.columns(5)
                c0.metric("Site elevation", f"{res['centre']} m")
                c1.metric("Mean elevation", f"{res['mean']} m")
                c2.metric("Min",            f"{res['min']} m")
                c3.metric("Max",            f"{res['max']} m")
                c4.metric("Std dev",        f"{res['std']} m")
                st.caption(f"{res['pixels']:,} pixels sampled · {dem_type}")

                ref_height, assessment_asl, terrain_corr = calc_reference_height(
                    res["centre"], res["mean"], tower_height
                )

                st.divider()
                st.subheader("Rime ice reference height")
                r1, r2, r3 = st.columns(3)
                r1.metric("Terrain correction", f"{terrain_corr} m",
                          help="max(0, site − mean). Zero if site is in a valley.")
                r2.metric("Reference height",   f"{ref_height} m",
                          help="terrain correction + 2/3 × structure height (ISO 12494 / FNA)")
                r3.metric("Assessment point",   f"{assessment_asl} m asl",
                          help="Absolute elevation of the 2/3-height assessment point")

                st.divider()
                diagram_buf = make_diagram(
                    res["centre"], res["mean"], tower_height, ref_height, assessment_asl
                )
                st.image(diagram_buf, use_container_width=True)

                st.divider()
                m = build_map(lat, lon, radius_km, res)
                st_folium(m, use_container_width=True, height=500, returned_objects=[])

            except requests.HTTPError as e:
                st.error(f"API error {e.response.status_code} — check your key and coordinates.")
            except Exception as e:
                st.error(f"Something went wrong: {e}")
