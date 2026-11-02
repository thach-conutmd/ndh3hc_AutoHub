"""Master Sheet columns with controls in WebFlow's General-tab information panels."""

# Fill Hardware part number, Development number and Lead Plant first, then the
# remaining controls in form order. (column, payload key, WebFlow label, control type)
HARDWARE_FIELDS = (
    ("AN", "hardware_part_number", "Hardware part number", "text"),
    ("AO", "development_number", "Development number", "text"),
    ("AV", "lead_plant", "Lead Plant", "dropdown"),
    ("AB", "vehicle_model", "Model", "text"),
    ("AG", "engine_family", "Engine family", "text"),
    ("AC", "power", "Power [kW]", "text"),
    ("AH", "emission_norm", "Emission norm", "multi"),
    ("AD", "immobilizer", "Immobilizer", "multi"),
    ("AI", "transmission", "Transmission", "multi"),
    ("AE", "displacement", "Displacement", "text"),
    ("AJ", "market", "Market", "multi"),
    ("AF", "model_year", "Model year", "multi"),
    ("AK", "cylinders", "Cylinders", "text"),
    ("AL", "project_number_first", "Project number (1st part, Customer Code Number)", "text"),
    ("AM", "project_number_second", "Project number (2nd part, Project Code Number)", "text"),
    ("AP", "ecu_hardware_name", "ECU hardware name", "text"),
    ("AQ", "customer_order_number", "Customer order number", "text"),
    ("AR", "customer_hardware_part_number", "Customer hardware part number", "text"),
    ("AS", "customer_software_part_number", "Customer software part number", "text"),
    ("AT", "car", "Car", "text"),
    ("AU", "customer_name", "Customer name", "text"),
    ("AY", "program_version", "Program version", "text"),
    ("AX", "software_part_number", "Software part number", "text"),
    ("AZ", "data_version", "Data version", "text"),
    ("AW", "ecr_number", "ECR number", "text"),
)

GENERAL_OPTION_COLUMNS = {
    column: key
    for column, key, _, kind in HARDWARE_FIELDS
    if kind == "multi"
}
