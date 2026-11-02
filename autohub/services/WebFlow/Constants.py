
WEBFLOW_TITLE               = "webFLOW"             # Title of the webFLOW page
WEBFLOW_TIMEOUT             = 60                    # Timeout in seconds for webFLOW page to load
WEBFLOW_REFRESH_INTERVAL    = 3                     # Interval in seconds to refresh the webFLOW page while waiting for it to load
WEBFLOW_MAX_ATTEMPTS        = 5                     # Maximum number of attempts to check for webFLOW page load
IMPLICIT_WAIT               = 1                     # Seconds Selenium waits for an element to show up when it is looked up
WEBFLOW_TIMEOUT_CSS         = 1                     # Timeout in seconds for CSS-based webFLOW page checks
WEBDRIVER_DOWNLOAD_PROXY    = "http://rb-proxy-apac.bosch.com:8080"  # Proxy used to download msedgedriver when no driver path is set

WEBFLOW_LOADING_SCREEN_CLASS        = "loading-screen-icon"
WEBFLOW_ACTIVITY_INDICATOR_CLASS    = "a-activity-indicator"
TOAST_MESSAGE_CSS                   = 'div[role="alert"].p-toast-message'  # A toast message such as "Saved successfully"


SIDEMENUBAR_TIMEOUT         = 60                    # Timeout in seconds for the side menu bar to load
SIDEMENUBAR_ID              = "sidemenubar"         # ID of the side menu bar
SIDEMENUBAR_ACTIVE          = "active"              # Identifier for the active state of the side menu bar
SIDEMENUBAR_HEADER_CLASS    = "sidebar-header"      # Class name for the header of the side menu bar
SIDEMENUBAR_BODY_CLASS      = "sidebar-content"     # Class name for the body of the side menu bar
SIDEMENUBAR_FOOTER_CLASS    = "sidebar-footer"      # Class name for the footer of the side menu bar
SIDEMENUBAR_OPEN_BTN_CSS       = 'button[aria-label="Open Menu"]'  # CSS selector for the open menu bar button
SIDEMENUBAR_CLOSE_BTN_CSS      = 'button[aria-label="Close Menu"]'  # CSS selector for the close menu bar button

SIDEMENUBAR_JOBCREATION_CSS = 'li[aria-label="Job Creation"]'  # CSS selector for the job creation section in the side menu bar
SIDEMENUBAR_JOBCREATION_NEWJOB_BTN_CSS = 'li[aria-label="New Job"]'  # CSS selector for the "New Job" button
SIDEMENUBAR_JOBCREATION_NEWJOBXML_BTN_CSS = 'li[aria-label="New Job from XML"]'  # CSS selector for the "New Job from XML" button


BODY_TIMEOUT                    = 10                    # Timeout in seconds for the body to load completely
SAVE_TIMEOUT                    = 30                    # Save confirmation may take longer than a regular page action
BODY_JOBCREATION_PAGE_CLASS     = "create-job-title"  # Class name of the body job creation page
BODY_JOBCREATION_BTN_CSS        = 'div[id*="_id_"]'              # CSS selector for the buttons in the body job creation form
BODY_JOBCREATION_CONFIRM_BTN_CSS   = 'button[label="Confirm"]'   # CSS selector for the "Confirm" button in the body job creation form
BODY_JOBCREATION_OPTIONS_CLASS  = "p-dropdown-items-wrapper"     # Class name for the options in the body job creation form
BODY_JOBCREATION_OPTIONS_MAX_ITEMS = 15                          # Maximum number of options in the body job creation form dropdown
BODY_JOBCREATION_ECUGEN_XPATH   = '//div[text()=" ECU Generation "]'                # XPath of the body job creation form
BODY_JOBCREATION_BRAND_XPATH    = '//div[text()=" Brand "]'                         # XPath of the body job creation form
BODY_JOBCREATION_ECUTYPE_XPATH  = '//div[text()=" ECU type "]'                      # XPath of the body job creation form
BODY_JOBCREATION_CUSTGRP_XPATH  = '//div[text()=" Customer group "]'                # XPath of the body job creation form
BODY_JOBCREATION_WRKMODE_XPATH  = '//div[text()=" Working mode "]'                  # XPath of the body job creation form
BODY_JOBCREATION_TOOLVER_XPATH  = '//div[text()=" Tool version "]'                  # XPath of the body job creation form
BODY_JOBCREATION_ROUTING_XPATH  = '//div[text()=" Routing "]'                       # XPath of the body job creation form
BODY_JOBCREATION_MAX_JOBS = 10                                 # "Number of jobs to create" offers 1-10; larger batches are created in groups
BODY_JOBCREATION_NUMBER_XPATH   = '//div[text()=" Number of jobs to create "]'      # XPath of the body job creation form

BODY_ACTION_RIBBON_CLASS = "action-ribbon"  # Class name for the action ribbon in the body

BODY_INFORMATION_TITLE_XPATH = '//span[text()=" Job information "]'     # XPath of the body information title
BODY_INFORMATION_BODY_CSS    = 'div[style^="display:"]'  # CSS selector for the body of the job information section


CUSTOMER_TAB_XPATH = '//a[text()="Customer"]'
FILES_TAB_XPATH = '//a[text()="Files"]'

CUSTOMER_SPECIFIC_PARAMS_TITLE_XPATH = '//span[text()=" Customer specific parameters "]'     # XPath of the body information title
CUSTOMER_SPECIFIC_PARAMS_BODY_CSS    = 'div[style^="display:"]'  # CSS selector for the body of the specific parameters section
CUSTOMER_ECU_DEFAULT_ID_INPUT_CSS_SELECTOR         = 'input[placeholder="ECU default ID"]'
CUSTOMER_ECU_PROGRAM_ID_INPUT_CSS_SELECTOR         = 'input[placeholder="ECU progam ID"]'
CUSTOMER_ECU_REWRITING_ID_INPUT_CSS_SELECTOR       = 'input[placeholder="ECU rewriting ID"]'
CUSTOMER_SECURITY_COEFFICIENT_INPUT_CSS_SELECTOR   = 'input[placeholder="Security coefficient"]'
CUSTOMER_SW_VERSION_INPUT_CSS_SELECTOR             = 'input[placeholder="SW version"]'
CUSTOMER_COMPONENT_ID_INPUT_CSS_SELECTOR           = 'input[placeholder="Component ID"]'

ECU_TAB_XPATH = '//a[text()="ECU"]'
ECU_TAB_OPTIONS_CLASS       = "p-dropdown-items-wrapper"     # Class name for the options in the body job creation form
ECU_TAB_BTN_CSS             = 'div[id*="_id_"]'              # CSS selector for the buttons in the body job creation form
ECU_TAB_OPTIONS_MAX_ITEMS   = 5                              # Maximum number of options in the body job creation form dropdown

ECU_FSW_CNT_SPECIFIC_PARAMS_TITLE_XPATH = '//span[text()=" FSW CNT Specific parameters "]'     # XPath of the body information title
ECU_FSW_CNT_SPECIFIC_PARAMS_BODY_CSS    = 'div[style^="display:"]'  # CSS selector for the body of the specific parameters section
ECU_INDI_SPEC_INPUT_CSS_SELECTOR                = 'input[placeholder="Specification-ID for PAV (INDI_SPEC)"]'
ECU_FAM_NAME_INPUT_CSS_SELECTOR                 = 'input[placeholder="Family name (FAM_NAME)"]'
ECU_FSWID_PROJECT_VERSION_INPUT_CSS_SELECTOR    = 'input[placeholder="FSWID Project Version 4 characters"]'
ECU_FSWID_PROGRAM_VERSION_INPUT_CSS_SELECTOR    = 'input[placeholder="FSWID Program Version 4 characters"]'

ECU_SPECIFIC_PARAMS_TITLE_XPATH = '//span[text()="  ECU specific parameters "]'     # XPath of the body information title
ECU_SPECIFIC_PARAMS_BODY_CSS    = 'div[style^="display:"]'  # CSS selector for the body of the specific parameters section
ECU_TP_LEVEL_TITLE_XPATH        = '//div[text()=" TP_Level "]'     # XPath of the TP Level title
ECU_DIAGNOSTIC_PROTOCOL_TITLE_XPATH = '//div[text()=" Diagnostic protocol "]'     # XPath of the diagnostic protocol title
ECU_PROJECT_LCTVORB_TITLE_XPATH     = '//div[text()=" Project with LCTVorb? "]'     # XPath of the Project LCTVorb title
ECU_PROJECT_LCTVORB_CHECKBOX_CSS    = 'div[role="checkbox"]'  # CSS selector for the body of the Project LCTVorb section


GENERAL_TAB_XPATH = '//a[text()="General"]'
GENERAL_TAB_OPTIONS_CLASS       = "p-dropdown-items-wrapper"     # Class name for the options in the body job creation form
GENERAL_TAB_BTN_CSS             = 'div[id*="_id_"]'              # CSS selector for the buttons in the body job creation form
GENERAL_TAB_OPTIONS_MAX_ITEMS   = 15                          # Maximum number of options in the body job creation form dropdown

GENERAL_CONFIGURATOR_ITEMS_TITLE_XPATH = '//span[text()=" Configurator items "]'     # XPath of the body information title
GENERAL_CONFIGURATOR_ITEMS_BODY_CSS    = 'div[style^="display:"]'  # CSS selector for the body of the specific parameters section
GENERAL_DELIVERY_TYPE_TITLE_XPATH       = '//div[text()=" Delivery Type "]'     # XPath of the TP Level title
GENERAL_RELEASE_CLASS_TITLE_XPATH       = '//div[text()=" Release class "]'     # XPath of the diagnostic protocol title
GENERAL_RELEASE_SCOPE_TITLE_XPATH       = '//div[text()=" Release scope "]'     # XPath of the TP Level title
GENERAL_LIMITATIONS_TITLE_XPATH         = '//div[text()=" Limitations "]'     # XPath of the diagnostic protocol title
GENERAL_SAFETY_MONITORING_SW_BY_RB_TITLE_XPATH     = '//div[text()=" Safety Monitoring SW by RB "]'     # XPath of the Project LCTVorb title
GENERAL_SAFETY_MONITORING_SW_BY_RB_CHECKBOX_CSS    = 'div[role="checkbox"]'  # CSS selector for the body of the Project LCTVorb section
GENERAL_SAFETY_CALIBRATION_RESPONSIBILITY_TITLE_XPATH     = '//div[text()=" Has Bosch responsibility for Safety Calibration?  "]'     # XPath of the Project LCTVorb title
GENERAL_SAFETY_CALIBRATION_RESPONSIBILITY_CHECKBOX_CSS    = 'div[role="checkbox"]'  # CSS selector for the body of the Project LCTVorb section
GENERAL_BOSCH_CAL_DATA_RESPONSIBILITY_TITLE_XPATH     = '//div[text()=" Has Bosch Cal Data Responsibility beside Safety Calibration?  "]'     # XPath of the Project LCTVorb title
GENERAL_BOSCH_CAL_DATA_RESPONSIBILITY_CHECKBOX_CSS    = 'div[role="checkbox"]'  # CSS selector for the body of the Project LCTVorb section
GENERAL_DATA_INTEGRATION_RESPONSIBILITY_TITLE_XPATH     = '//div[text()=" Is Bosch responsible for data integration? "]'     # XPath of the Project LCTVorb title
GENERAL_DATA_INTEGRATION_RESPONSIBILITY_CHECKBOX_CSS    = 'div[role="checkbox"]'  # CSS selector for the body of the Project LCTVorb section
