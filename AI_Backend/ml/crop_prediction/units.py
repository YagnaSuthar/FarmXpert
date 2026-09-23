"""Unit conversion between sensor hardware output and dataset units.

The dashboard sensor reports NPK in mg/kg while the FarmX dataset expresses
fertiliser dose in kg/ha.  The user is reconfiguring the sensor to emit kg/ha
directly, so `mg_kg_to_kg_ha` is kept as an escape hatch rather than being
applied by default.
"""

# Typical Indian agricultural topsoil, 0-15 cm plough layer.
DEFAULT_BULK_DENSITY = 1.35   # g/cm3
DEFAULT_DEPTH_CM = 15.0


def mg_kg_to_kg_ha(mg_per_kg, bulk_density=DEFAULT_BULK_DENSITY,
                   depth_cm=DEFAULT_DEPTH_CM):
    """Convert a soil concentration (mg/kg) to an areal load (kg/ha).

    One hectare of soil `depth_cm` deep weighs
    10_000 m2 * depth_m * bulk_density t/m3 tonnes.
    """
    soil_mass_t_per_ha = 10_000 * (depth_cm / 100.0) * bulk_density
    return mg_per_kg * soil_mass_t_per_ha / 1000.0


def us_cm_to_ds_m(micro_siemens_per_cm):
    """Soil EC: 1 dS/m == 1000 uS/cm."""
    return micro_siemens_per_cm / 1000.0


def ds_m_to_us_cm(ds_per_m):
    return ds_per_m * 1000.0
