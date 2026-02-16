from app.core.i18n import I18N


def test_i18n_switch_language() -> None:
    i18n = I18N("zh")
    assert i18n.t("tab.merge") in {"素材合并", "Merge"}
    i18n.set_language("ja")
    assert i18n.t("tab.settings") in {"設定", "Settings"}
    i18n.set_language("en")
    assert i18n.t("tab.download") in {"Download", "Video Download"}
