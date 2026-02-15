<script>
	let { data } = $props();
</script>

{#if data?.hits?.length}
<table>
	<thead>
		<tr>
			<th>Hit</th>
			<th>Identity</th>
			<th>Coverage</th>
			<th>E-value</th>
			<th></th>
		</tr>
	</thead>
	<tbody>
		{#each data.hits as hit}
		<tr>
			<td class="name">{hit.name}</td>
			<td>{hit.identity}%</td>
			<td>{hit.coverage}%</td>
			<td>{hit.evalue}</td>
			<td><button>View</button></td>
		</tr>
		{/each}
	</tbody>
</table>
{:else}
<p class="empty">No BLAST hits found</p>
{/if}

<style>
	table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
	th, td { padding: 0.4rem 0.6rem; text-align: left; border-bottom: 1px solid #f0f0f0; }
	th { font-weight: 600; color: #888; font-size: 0.75rem; text-transform: uppercase; }
	.name { font-weight: 500; }
	button { font-size: 0.75rem; padding: 0.2rem 0.6rem; cursor: pointer; border: 1px solid #ddd; background: white; border-radius: 4px; }
	.empty { color: #aaa; font-size: 0.85rem; }
</style>
