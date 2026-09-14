import { defineConfig } from "vitest/config";

export default defineConfig({
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
