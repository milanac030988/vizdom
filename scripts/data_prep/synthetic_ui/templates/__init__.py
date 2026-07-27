"""UI templates for synthetic dataset generation."""

from .base import UITemplate
from .login_form import LoginFormTemplate
from .settings_panel import SettingsPanelTemplate
from .dashboard import DashboardTemplate
from .toolbar import ToolbarTemplate
from .dialog import DialogTemplate
from .data_table import DataTableTemplate
from .form_sidebar import FormSidebarTemplate
from .info_panel import InfoPanelTemplate
from .car_cluster import CarClusterTemplate

TEMPLATE_REGISTRY = {
    "login": LoginFormTemplate,
    "settings": SettingsPanelTemplate,
    "dashboard": DashboardTemplate,
    "toolbar": ToolbarTemplate,
    "dialog": DialogTemplate,
    "data_table": DataTableTemplate,
    "form_sidebar": FormSidebarTemplate,
    "info_panel": InfoPanelTemplate,
    "car_cluster": CarClusterTemplate,
}

__all__ = [
    "UITemplate",
    "TEMPLATE_REGISTRY",
    "LoginFormTemplate",
    "SettingsPanelTemplate",
    "DashboardTemplate",
    "ToolbarTemplate",
    "DialogTemplate",
    "DataTableTemplate",
]
