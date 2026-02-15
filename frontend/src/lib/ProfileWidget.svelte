<script>
	let { data } = $props();
</script>

{#if data?.sequence}
<div class="profile">
	<div class="field"><strong>Name:</strong> {data.sequence.name}</div>
	<div class="field"><strong>Size:</strong> {data.sequence.size_bp} bp</div>
	<div class="field"><strong>Topology:</strong> {data.sequence.topology}</div>

	{#if data.sequence.description}
	<div class="field"><strong>Description:</strong> {data.sequence.description}</div>
	{/if}

	{#if data.features?.length}
	<h4>Features</h4>
	<table>
		<thead>
			<tr><th>Name</th><th>Type</th><th>Location</th><th>Strand</th></tr>
		</thead>
		<tbody>
			{#each data.features as feat}
			<tr>
				<td>{feat.name}</td>
				<td>{feat.type}</td>
				<td>{feat.start}..{feat.end}</td>
				<td>{feat.strand > 0 ? '+' : '\u2212'}</td>
			</tr>
			{/each}
		</tbody>
	</table>
	{/if}

	{#if data.primers?.length}
	<h4>Primers</h4>
	<table>
		<thead>
			<tr><th>Name</th><th>Sequence</th><th>Tm</th></tr>
		</thead>
		<tbody>
			{#each data.primers as p}
			<tr>
				<td>{p.name}</td>
				<td class="mono">{p.sequence}</td>
				<td>{p.tm ? p.tm.toFixed(1) + '\u00B0C' : '\u2014'}</td>
			</tr>
			{/each}
		</tbody>
	</table>
	{/if}
</div>
{:else}
<p class="empty">Sequence not found</p>
{/if}

<style>
	.profile { font-size: 0.85rem; }
	.field { margin-bottom: 0.3rem; }
	h4 { margin: 0.75rem 0 0.3rem; font-size: 0.85rem; color: #666; }
	table { width: 100%; border-collapse: collapse; }
	th, td { padding: 0.3rem 0.5rem; text-align: left; border-bottom: 1px solid #f0f0f0; }
	th { font-weight: 600; color: #888; font-size: 0.75rem; text-transform: uppercase; }
	.mono { font-family: 'SF Mono', Monaco, monospace; font-size: 0.78rem; }
	.empty { color: #aaa; font-size: 0.85rem; }
</style>
