<script>
	import { sendRawMessage, submitForm, cancelForm } from '$lib/stores/chat.ts';

	let { data, messageIndex = -1 } = $props();

	const schema = $derived(data?.schema || {});
	const toolName = $derived(data?.tool_name || '');
	const properties = $derived(schema.properties || {});
	const required = $derived(new Set(schema.required || []));

	let values = $state({});
	let tags = $state({}); // key → string[] for array, {k:v}[] for object

	function addTag(field, inputEl) {
		const raw = inputEl.value.trim();
		if (!raw) return;
		if (!tags[field]) tags[field] = [];

		const prop = properties[field];
		if (prop?.type === 'object') {
			// Parse "key: value" or "key:value"
			const sep = raw.indexOf(':');
			if (sep < 1) return;
			const k = raw.slice(0, sep).trim();
			const v = raw.slice(sep + 1).trim();
			if (!k || !v) return;
			// Remove existing tag with same key
			tags[field] = tags[field].filter((t) => t.key !== k);
			tags[field] = [...tags[field], { key: k, value: v }];
		} else {
			// array — just add the string
			if (!tags[field].includes(raw)) {
				tags[field] = [...tags[field], raw];
			}
		}
		inputEl.value = '';
	}

	function removeTag(field, index) {
		tags[field] = tags[field].filter((_, i) => i !== index);
	}

	function handleTagKeydown(field, e) {
		if (e.key === 'Enter' || e.key === ',') {
			e.preventDefault();
			addTag(field, e.target);
		}
		// Backspace on empty input removes last tag
		if (e.key === 'Backspace' && !e.target.value && tags[field]?.length) {
			tags[field] = tags[field].slice(0, -1);
		}
	}

	function handleSubmit(e) {
		e.preventDefault();
		const params = {};

		for (const [key, prop] of Object.entries(properties)) {
			if (prop.type === 'array' || prop.type === 'object') {
				const items = tags[key];
				if (!items?.length) continue;
				if (prop.type === 'object') {
					const obj = {};
					for (const t of items) {
						// Try to parse numeric values
						const num = Number(t.value);
						obj[t.key] = isNaN(num) ? t.value : num;
					}
					params[key] = obj;
				} else {
					params[key] = items;
				}
			} else {
				const val = values[key];
				if (val === '' || val === undefined) continue;
				if (prop.type === 'number' || prop.type === 'integer') {
					params[key] = Number(val);
				} else {
					params[key] = val;
				}
			}
		}

		const commandText = `//${toolName} ${JSON.stringify(params)}`;
		if (messageIndex >= 0) {
			submitForm(messageIndex, commandText);
		}
		sendRawMessage(commandText);
	}

	function tagPlaceholder(prop) {
		if (prop.type === 'object') return 'key: value, then Enter';
		return 'value, then Enter';
	}
</script>

<form class="form-widget" onsubmit={handleSubmit}>
	{#each Object.entries(properties) as [key, prop]}
		<div class="field">
			<label for={key}>
				{key}
				{#if required.has(key)}<span class="req">*</span>{/if}
			</label>
			{#if prop.description}
				<span class="desc">{prop.description}</span>
			{/if}

			{#if prop.type === 'boolean'}
				<input type="checkbox" id={key} bind:checked={values[key]} />
			{:else if prop.type === 'number' || prop.type === 'integer'}
				<input
					type="number"
					id={key}
					step={prop.type === 'integer' ? '1' : 'any'}
					placeholder={prop.default != null ? String(prop.default) : ''}
					bind:value={values[key]}
				/>
			{:else if prop.type === 'array' || prop.type === 'object'}
				<label class="tag-input" for="{key}-tag">
					{#each tags[key] || [] as tag, i}
						<button type="button" class="tag" onclick={() => removeTag(key, i)}>
							{#if prop.type === 'object'}
								<span class="tag-key">{tag.key}:</span> {tag.value}
							{:else}
								{tag}
							{/if}
							<span class="tag-x">&times;</span>
						</button>
					{/each}
					<input
						id="{key}-tag"
						type="text"
						placeholder={tagPlaceholder(prop)}
						onkeydown={(e) => handleTagKeydown(key, e)}
						onblur={(e) => addTag(key, e.target)}
					/>
				</label>
			{:else}
				<textarea
					id={key}
					rows={key === 'sequence' ? 4 : 1}
					placeholder={prop.default != null ? String(prop.default) : ''}
					bind:value={values[key]}
				></textarea>
			{/if}
		</div>
	{/each}
	<div class="form-actions">
		<button type="submit">Run {toolName}</button>
		<button type="button" class="cancel-btn" onclick={() => cancelForm(messageIndex)}>Cancel</button>
	</div>
</form>

<style>
	.form-widget {
		display: flex;
		flex-direction: column;
		gap: 0.6rem;
		font-size: 0.85rem;
	}

	.field {
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
	}

	label {
		font-weight: 600;
		color: #555;
		font-size: 0.8rem;
	}

	.req {
		color: #dc2626;
		margin-left: 0.1rem;
	}

	.desc {
		color: #999;
		font-size: 0.75rem;
	}

	input, textarea {
		border: 1px solid #ddd;
		border-radius: 4px;
		padding: 0.35rem 0.5rem;
		font-family: inherit;
		font-size: 0.82rem;
		outline: none;
		resize: vertical;
	}

	input:focus, textarea:focus {
		border-color: #999;
	}

	input[type="checkbox"] {
		width: auto;
		align-self: flex-start;
	}

	label.tag-input {
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem;
		border: 1px solid #ddd;
		border-radius: 4px;
		padding: 0.25rem 0.4rem;
		cursor: text;
		min-height: 2rem;
		align-items: center;
	}

	label.tag-input:focus-within {
		border-color: #999;
	}

	label.tag-input input {
		border: none;
		outline: none;
		padding: 0.15rem 0;
		font-size: 0.82rem;
		flex: 1;
		min-width: 8rem;
	}

	.tag {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		background: #e8e8e8;
		border: none;
		border-radius: 3px;
		padding: 0.15rem 0.4rem;
		font-size: 0.78rem;
		font-family: inherit;
		cursor: pointer;
		color: #333;
	}

	.tag:hover {
		background: #d0d0d0;
	}

	.tag-key {
		font-weight: 600;
	}

	.tag-x {
		color: #999;
		font-size: 0.9em;
		margin-left: 0.1rem;
	}

	.form-actions {
		display: flex;
		gap: 0.5rem;
		margin-top: 0.2rem;
	}

	.form-actions button {
		padding: 0.4rem 1rem;
		border: none;
		border-radius: 6px;
		cursor: pointer;
		font-size: 0.82rem;
	}

	button[type="submit"] {
		background: #333;
		color: white;
	}

	button[type="submit"]:hover {
		background: #555;
	}

	.cancel-btn {
		background: #e8e8e8;
		color: #666;
	}

	.cancel-btn:hover {
		background: #ddd;
	}
</style>
