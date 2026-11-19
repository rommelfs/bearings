# Bearings administration

The platform backend at `/admin/` uses **Bearings administration** in the browser title and the Bearings wordmark/header. Its system font, teal/navy colors, surfaces and sidebar follow the workspace's appearance. The supported Django admin layout remains underneath, including user/group permissions, filtered selectors, related-object popups, history, password forms, CSRF protection and responsive controls.

Use **Back to Bearings** to return to the workspace. Platform superusers additionally see **Registrations** and **Service mail & local outbox** links. These links do not grant permissions. Existing staff/model permissions and the platform-only organization/connector administration policy still apply.

The admin theme switch retains light, dark and automatic choices. Keyboard focus and mobile layouts remain supported. The dedicated `portal/admin.css` avoids applying general workspace layout rules to specialized admin widgets. An override of `admin/base_site.html` supplies the brand/navigation; explicit template-directory precedence lets it load ahead of the stock admin template without rearranging installed apps or duplicating admin form templates.

After updating a retained lab, use `python3 scripts/dev.py up --no-build` to reload the template settings. No migration or new dependency is needed. The existing portal template/static directories are already mounted by the lab, so the theme requires no additional Docker volume. [Light appearance](../images/bearings-admin-light-1440.png) · [Dark appearance](../images/bearings-admin-dark-1440.png).
