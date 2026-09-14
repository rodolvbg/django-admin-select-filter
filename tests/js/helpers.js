import { vi } from "vitest";

export function addFilter(extraAttrs = "") {
	document.body.innerHTML = `
    <select
      class="django-admin-select-filter"
      data-placeholder="Search"
      data-jquery-url="/jquery.js"
      data-jquery-init-url="/jquery.init.js"
      data-select2-url="/select2.js"
      ${extraAttrs}
    ></select>
  `;
}

export function addAsyncFilter(extraAttrs = "") {
	addFilter(`
      data-async-call="true"
      data-api-url="/admin/select-filter/options/"
      data-app-label="testapp"
      data-model-name="book"
      data-parameter-name="author"
      data-all-value="__all__"
      ${extraAttrs}
  `);
}

export function addMultipleFilter(extraAttrs = "") {
	document.body.innerHTML = `
    <select
      class="django-admin-select-filter"
      multiple
      data-placeholder="Search"
      data-jquery-url="/jquery.js"
      data-jquery-init-url="/jquery.init.js"
      data-select2-url="/select2.js"
      data-parameter-name="author"
      data-all-value="__all__"
      data-multiple="true"
      data-multiple-separator=","
      ${extraAttrs}
    ></select>
  `;
}

export function addNonSearchableFilter() {
	addFilter('data-searchable="false"');
}

export function mockLocationAssign() {
	const assign = vi.fn();
	const original = window.location;
	Object.defineProperty(window, "location", {
		configurable: true,
		value: { ...original, assign },
	});
	return {
		assign,
		restore: () => {
			Object.defineProperty(window, "location", {
				configurable: true,
				value: original,
			});
		},
	};
}

export function installDjangoJQuery({
	select2Installed = true,
	val = null,
} = {}) {
	const select2 = vi.fn();
	const on = vi.fn();
	const valFn = vi.fn(() => val);
	const jquery = vi.fn(() => ({ select2, on, val: valFn }));
	jquery.fn = select2Installed ? { select2: vi.fn() } : {};
	window.django = { jQuery: jquery };
	return { jquery, on, select2, val: valFn };
}

export function resetJsEnvironment() {
	document.head.innerHTML = "";
	document.body.innerHTML = "";
	delete window.django;
	delete window.jQuery;
	delete window.$;
	delete window.__djangoAdminSelectFilterPlugins;
	window.history.replaceState({}, "", "/");
	// core.js defers its own initialization until DOMContentLoaded (see
	// fireDomReady below) so that every capability module a filter's
	// attributes requested — each its own <script type="module"> tag in
	// base.html — has had a chance to register itself first, regardless of
	// tag order. Real page loads reach "loading" naturally at this point;
	// mimic that here since jsdom's document starts out already "complete".
	Object.defineProperty(document, "readyState", {
		configurable: true,
		get: () => "loading",
	});
}

// Simulates the browser reaching DOMContentLoaded once every module script
// has executed, triggering core.js's deferred initializeFilters(). Awaiting
// a macrotask afterwards lets the resulting promise chain (ensureSelect2Loaded
// -> the per-filter loop) fully settle before assertions run.
export async function fireDomReady() {
	document.dispatchEvent(new Event("DOMContentLoaded"));
	await new Promise((resolve) => setTimeout(resolve, 0));
}
