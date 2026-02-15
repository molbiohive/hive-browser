<script>
	import { sendMessage } from '$lib/stores/chat.ts';

	let { data } = $props();

	const schema = data?.schema || {};
	const toolName = data?.tool_name || '';
	const properties = schema.properties || {};
	const required = new Set(schema.required || []);

	let values = $state({});

	function handleSubmit(e) {
		e.preventDefault();
		const params = {};
		for (const [key, val] of Object.entries(values)) {
			if (val !== '' && val !== undefined) {
				const prop = properties[key];
				if (prop?.type === 'number' || prop?.type === 'integer') {
					params[key] = Number(val);
				} else {
					params[key] = val;
				}
			}
		}
		sendMessage(`//${toolName} ${JSON.stringify(params)}`);
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
	<button type="submit">Run {toolName}</button>
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

	button {
		align-self: flex-start;
		padding: 0.4rem 1rem;
		background: #333;
		color: white;
		border: none;
		border-radius: 6px;
		cursor: pointer;
		font-size: 0.82rem;
		margin-top: 0.2rem;
	}

	button:hover {
		background: #555;
	}
</style>
