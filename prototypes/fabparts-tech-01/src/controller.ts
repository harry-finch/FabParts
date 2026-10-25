export type Library = { id: string; name: string; count: number };
export type BusinessState = 'DRAFT' | 'IDENTIFIED' | 'DEPRECATED';
export type Component = {
  id: string; reference: string; mpn: string; manufacturer: string; description: string;
  category: string; package: { id: string; name: string } | null;
  libraries: { id: string; name: string }[]; state: BusinessState;
};
export type Asset = {
  id: string; name: string; type: string; origin: string; source: string; owner: string;
  validation_state: string; selected: boolean;
  file: { sha256: string; name: string; size_bytes: number } | null;
};
export type Selection = { type: string; owner: string; asset_id: string | null;
  external: { name: string; library: string; relative_path: string; sha256: string; origin: string } | null };
export type Detail = Component & { associated_assets: Asset[]; selections: Selection[];
  documents: { id: string; asset_id: string; title: string; revision: string; language: string; date: string; kind: string }[];
  qualification: null; preview_available: false };
export type Health = { workspace_mode?: "personal"|"sandbox"|"readonly"; status: string; engine_version: string; protocol_version: number; read_only: boolean; qt_loaded: boolean; schema: string; pid: number };
export type Query = { library: string; search: string; category: string; package: string; state: string; limit: number; offset: number };
export const defaultQuery = (): Query => ({library:'all',search:'',category:'',package:'',state:'',limit:50,offset:0});
export type Page = { components: Component[]; total: number; offset: number; limit: number; facets: { categories: string[]; packages: string[] } };
export type Snapshot = { phase: 'starting' | 'ready' | 'failed'; loading: boolean; detailLoading: boolean;
  libraries: Library[]; page: Page; detail: Detail | null; selectedId: string;
  health: Health | null; error: { code: string; message: string } | null };
export const initial = (): Snapshot => ({phase:'starting',loading:false,detailLoading:false,libraries:[],
  page:{components:[],total:0,offset:0,limit:50,facets:{categories:[],packages:[]}},detail:null,selectedId:'',health:null,error:null});
export type Transport = <T>(command: string, args?: Record<string, unknown>) => Promise<T>;

// Async view state, with no domain rules, fixture fallback or persistent catalogue.
export class Controller {
  state = initial();
  query = defaultQuery();
  dataDir: string | undefined;
  private request = 0;
  private selection = 0;
  private generation = 0;
  private checkingHealth = false;
  private preferredId = "";
  private invoke: Transport;
  private changed: (state: Snapshot) => void;
  constructor(invoke: Transport, changed: (state: Snapshot) => void) { this.invoke = invoke; this.changed = changed; }
  private emit(patch: Partial<Snapshot>) { this.state = {...this.state,...patch}; this.changed(this.state); }
  private fail(error: unknown) {
    this.request++; this.selection++;
    const e = error as {code?: string; message?: string};
    this.emit({...initial(),phase:'failed',error:{code:e?.code || 'CONNECTION_ERROR',message:e?.message || String(error)}});
  }
  async start() {
    const generation = ++this.generation;
    this.request++; this.selection++;
    this.emit(initial());
    try {
      const health = await this.invoke<Health>('restart_engine', this.dataDir ? {dataDir:this.dataDir} : undefined);
      if (generation !== this.generation) return;
      const libraries = await this.invoke<Library[]>('list_libraries');
      if (generation !== this.generation) return;
      this.emit({phase:'ready',health,libraries});
      await this.load(this.query);
    } catch (e) { if (generation === this.generation) this.fail(e); }
  }
  async load(query: Query) {
    this.query = {...query};
    if (this.state.phase !== 'ready') return;
    const token = ++this.request;
    this.selection++;
    this.emit({loading:true,detail:null,selectedId:'',detailLoading:false});
    try {
      const page = await this.invoke<Page>('list_components',{query});
      if (token !== this.request) return;
      this.emit({page,loading:false});
      if (page.components[0]) await this.select(page.components.find(c=>c.id===this.preferredId)?.id || page.components[0].id);
    } catch (e) { if (token === this.request) this.fail(e); }
  }
  async select(id: string) {
    this.preferredId=id;
    const token = ++this.selection;
    this.emit({selectedId:id,detail:null,detailLoading:true});
    try {
      const detail = await this.invoke<Detail>('get_component',{id});
      if (token === this.selection) this.emit({detail,detailLoading:false});
    } catch (e) { if (token === this.selection) this.fail(e); }
  }
  async saved(id:string) {
    const generation=this.generation;
    try {
      const detail=await this.invoke<Detail>('get_component',{id});
      const libraries=await this.invoke<Library[]>('list_libraries');
      if(generation!==this.generation)return;
      this.preferredId=id;this.emit({libraries});
      await this.load({...defaultQuery(),search:detail.reference});
      if(generation===this.generation && this.state.phase==='ready')await this.select(id);
    }catch(error){if(generation===this.generation)this.fail(error);}
  }
  async heartbeat() {
    if (this.checkingHealth || this.state.phase !== 'ready' || this.state.loading || this.state.detailLoading) return;
    const generation = this.generation;
    this.checkingHealth = true;
    try { await this.invoke<Health>('health'); }
    catch (e) { if (generation === this.generation) this.fail(e); }
    finally { this.checkingHealth = false; }
  }
  dispose() { this.generation++; this.request++; this.selection++; }
}
