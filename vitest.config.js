import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
	resolve: {
		alias: {
			// Mirrors the <script type="importmap"> base.html renders (see
			// BaseSelectFilter.media / _import_map_script), which lets the
			// other JS modules import core.js by bare specifier instead of a
			// relative path — Vite has no such import map for tests, so this
			// alias stands in for it.
			core: fileURLToPath(
				new URL(
					"src/django_admin_select_filter/static/admin_select_filter/js/core.js",
					import.meta.url,
				),
			),
		},
	},
	test: {
		environment: "jsdom",
		include: ["tests/js/**/*.test.js"],
		coverage: {
			provider: "v8",
			include: [
				"src/django_admin_select_filter/static/admin_select_filter/js/**",
			],
		},
	},
});
