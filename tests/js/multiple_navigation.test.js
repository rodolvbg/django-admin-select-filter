import { beforeEach, describe, expect, it, vi } from "vitest";
import {
	addMultipleFilter,
	fireDomReady,
	installDjangoJQuery,
	mockLocationAssign,
	resetJsEnvironment,
} from "./helpers.js";

const corePath =
	"../../src/django_admin_select_filter/static/admin_select_filter/js/core.js";
const multipleNavigationPath =
	"../../src/django_admin_select_filter/static/admin_select_filter/js/multiple_navigation.js";

describe("multiple_navigation", () => {
	beforeEach(() => {
		vi.resetModules();
		resetJsEnvironment();
	});

	it("registers a select2:close handler instead of select2:select", async () => {
		addMultipleFilter();
		const { on } = installDjangoJQuery();
		await import(multipleNavigationPath);
		await import(corePath);
		await fireDomReady();

		expect(
			on.mock.calls.some(([eventName]) => eventName === "select2:close"),
		).toBe(true);
		expect(
			on.mock.calls.some(([eventName]) => eventName === "select2:select"),
		).toBe(false);
	});

	it("joins every selected value on close", async () => {
		addMultipleFilter();
		const { on } = installDjangoJQuery({ val: ["1", "2"] });
		window.history.replaceState({}, "", "/admin/testapp/book/?p=2");
		const { assign, restore } = mockLocationAssign();
		try {
			await import(multipleNavigationPath);
			await import(corePath);
			await fireDomReady();
			const closeHandler = on.mock.calls.find(
				([eventName]) => eventName === "select2:close",
			)[1];

			closeHandler();

			const url = new URL(assign.mock.calls[0][0]);
			expect(url.searchParams.get("author")).toBe("1,2");
			expect(url.searchParams.has("p")).toBe(false);
		} finally {
			restore();
		}
	});

	it("clears the parameter when nothing is selected", async () => {
		addMultipleFilter();
		const { on } = installDjangoJQuery({ val: null });
		window.history.replaceState({}, "", "/admin/testapp/book/?author=1,2");
		const { assign, restore } = mockLocationAssign();
		try {
			await import(multipleNavigationPath);
			await import(corePath);
			await fireDomReady();
			const closeHandler = on.mock.calls.find(
				([eventName]) => eventName === "select2:close",
			)[1];

			closeHandler();

			const url = new URL(assign.mock.calls[0][0]);
			expect(url.searchParams.has("author")).toBe(false);
		} finally {
			restore();
		}
	});
});
