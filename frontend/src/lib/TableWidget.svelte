<script>
	let { data } = $props();
</script>

{#if data?.results?.length}
<table>
	<thead>
		<tr>
			<th>Name</th>
			<th>Size</th>
			<th>Topology</th>
			<th>Features</th>
			<th>Resistance</th>
			<th></th>
		</tr>
	</thead>
	<tbody>
		{#each data.results as row}
		<tr>
			<td class="name">{row.name}</td>
			<td>{(row.size_bp / 1000).toFixed(1)}kb</td>
			<td>{row.topology}</td>
			<td>{row.features?.join(', ') || ''}</td>
			<td>{row.resistance?.join(', ') || ''}</td>
			<td><button>View</button></td>
		</tr>
		{/each}
	</tbody>
</table>
{:else}
<p class="empty">No results</p>
{/if}

<style>
	table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
	th, td { padding: 0.4rem 0.6rem; text-align: left; border-bottom: 1px solid #f0f0f0; }
	th { font-weight: 600; color: #888; font-size: 0.75rem; text-transform: uppercase; }
	.name { font-weight: 500; }
	button { font-size: 0.75rem; padding: 0.2rem 0.6rem; cursor: pointer; border: 1px solid #ddd; background: white; border-radius: 4px; }
	.empty { color: #aaa; font-size: 0.85rem; }
</style>
