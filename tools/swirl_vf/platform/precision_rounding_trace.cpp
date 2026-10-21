// Focused self-authored P5 face-0/GID-2 diagnostic, never font acceptance.
// args: normalized-scaled-reference.{ttf,ttc} nominal-target.{ttf,ttc} summary.json
//       [--f2-witness]
// Reuse this repository's readback/geometry/SHA helpers without changing its
// existing probe, modes, thresholds, or entry point.
// Primary API/units references inspected before implementation:
// https://learn.microsoft.com/en-us/windows/win32/api/dwrite/nf-dwrite-idwritefontface-getdesignglyphmetrics
// https://learn.microsoft.com/en-us/windows/win32/api/dwrite/ns-dwrite-dwrite_glyph_metrics
// https://learn.microsoft.com/en-us/windows/win32/api/dwrite/nf-dwrite-idwritefontface-getglyphrunoutline
#define main swirl_transport_unused_stub_entry
#define wmain swirl_transport_unused_windows_entry
#include "target_axis_transport.cpp"
#undef wmain
#undef main

#if !defined(_WIN32)
int main() { return swirl_transport_unused_stub_entry(); }
#else
// This deliberately accepts only the seven-GID authored fixture. It does not
// publish raw measurements from the 47,102-GID original or converted font.
struct TraceFont final {
    HANDLE handle=INVALID_HANDLE_VALUE;
    std::vector<uint8_t> bytes;
    FaceData face;
    UINT32 face_count=1;
    std::string digest;
    std::vector<uint8_t> read() const {
        LARGE_INTEGER size{},zero{};
        need(GetFileSizeEx(handle,&size) && size.QuadPart>=12 && size.QuadPart<=64*1024*1024,
             "trace_fixture_size_out_of_scope");
        need(SetFilePointerEx(handle,zero,nullptr,FILE_BEGIN),"trace_fixture_seek_failed");
        std::vector<uint8_t> result(size_t(size.QuadPart));DWORD got=0;
        need(ReadFile(handle,result.data(),DWORD(result.size()),&got,nullptr) && got==result.size(),
             "trace_fixture_read_failed");
        return result;
    }
    const uint8_t* table(const char* name,size_t minimum) const {
        auto found=face.tables.find(tableTag(name));
        need(found!=face.tables.end() && found->second.second>=minimum,"trace_table_missing");
        return bytes.data()+found->second.first;
    }
    TraceFont(const fs::path& path,bool reference) {
        handle=CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,
                           FILE_ATTRIBUTE_NORMAL,nullptr);
        need(handle!=INVALID_HANDLE_VALUE,"trace_fixture_lock_failed");
        try {
            bytes=read();digest=sha(bytes);size_t directory=0;
            if(std::memcmp(bytes.data(),"ttcf",4)==0) {
                need(be32(bytes.data()+4)==0x10000 || be32(bytes.data()+4)==0x20000,
                     "trace_ttc_version");
                face_count=be32(bytes.data()+8);
                need(face_count>=1 && face_count<=32 && 12+size_t(face_count)*4<=bytes.size(),
                     "trace_ttc_face_count");
                directory=be32(bytes.data()+12);
            }
            need(directory<=bytes.size() && bytes.size()-directory>=12 &&
                 be32(bytes.data()+directory)==0x10000,"trace_glyf_sfnt_required");
            unsigned count=be16(bytes.data()+directory+4);
            need(count && count<=256 && 12+size_t(count)*16<=bytes.size()-directory,
                 "trace_table_directory");
            for(unsigned i=0;i<count;++i) {
                auto p=bytes.data()+directory+12+16*i;
                UINT32 offset=be32(p+8),length=be32(p+12);
                need(offset<=bytes.size() && length<=bytes.size()-offset &&
                     face.tables.emplace(tag(p),std::make_pair(offset,length)).second,
                     "trace_table_range_or_duplicate");
            }
            face.glyphs=be16(table("maxp",6)+4);face.upm=be16(table("head",20)+18);
            need(face.glyphs==7 && face.upm>=1000 && face.upm<=16384 && face.upm%1000==0,
                 "trace_authored_seven_GID_integer_UPM_grid_required");
            auto p=table("fvar",16);UINT32 offset=be16(p+4),stride=be16(p+10);
            UINT32 length=face.tables.at(tableTag("fvar")).second;
            need(be16(p)==1 && be16(p+8)==3 && stride>=20 && offset<=length &&
                 3*stride<=length-offset,"trace_fvar_structure");
            for(unsigned a=0;a<3;++a) {
                auto row=p+offset+a*stride;
                need(tag(row)==(reference?Q_TAGS[a]:USER_TAGS[a]),"trace_axis_tag_or_order");
                face.axes[a]={int32_t(be32(row+4))/65536.,int32_t(be32(row+8))/65536.,
                              int32_t(be32(row+12))/65536.};
                auto axis=face.axes[a];need(axis.lo<axis.value && axis.value<axis.hi,"trace_axis_range");
                if(reference) need(axis.lo==-1 && axis.value==0 && axis.hi==1,"trace_reference_axis_range");
            }
        } catch(...) { CloseHandle(handle);handle=INVALID_HANDLE_VALUE;throw; }
    }
    ~TraceFont() { if(handle!=INVALID_HANDLE_VALUE) CloseHandle(handle); }
    void unchanged() const { need(sha(read())==digest,"trace_fixture_changed"); }
    void identity(IDWriteFontFace5* actual) const {
        need(actual->GetIndex()==0 && actual->GetGlyphCount()==7 &&
             actual->GetSimulations()==DWRITE_FONT_SIMULATIONS_NONE,"trace_native_face_identity");
        for(auto item:face.tables) {
            const void* data=nullptr;UINT32 size=0;void* context=nullptr;BOOL exists=FALSE;
            checked(actual->TryGetFontTable(item.first,&data,&size,&context,&exists),"trace_native_table_failed");
            bool equal=exists && size==item.second.second && (!size ||
                std::memcmp(data,bytes.data()+item.second.first,size)==0);
            if(context) actual->ReleaseFontTable(context);
            need(equal,"trace_native_table_identity");
        }
    }
};

static const std::array<const char*,7> FIELD_NAMES{{"leftSideBearing","advanceWidth","rightSideBearing",
    "topSideBearing","advanceHeight","bottomSideBearing","verticalOriginY"}};
static ComPtr<Geometry> trace_outline(IDWriteFontFace5* face,float em,BOOL sideways,
                                      unsigned count,const float* advances) {
    const std::array<UINT16,2> gids{{2,2}};ComPtr<Geometry> out;out.Attach(new Geometry);
    checked(face->GetGlyphRunOutline(em,gids.data(),advances,nullptr,count,sideways,FALSE,out.Get()),
            "trace_native_outline_failed");
    checked(out->Close(),"trace_outline_nonfinite");return out;
}
static void write_points(std::ostream& out,const Geometry& geometry,double em) {
    out<<"{\"structure\":[";
    for(size_t i=0;i<geometry.structure.size();++i) { if(i) out<<',';out<<geometry.structure[i]; }
    out<<"],\"points_DIP\":[";
    for(size_t i=0;i<geometry.points.size();++i) {
        if(i) out<<',';auto p=geometry.points[i];out<<'['<<p.x<<','<<p.y<<']';
    }
    out<<"],\"points_original_source_font_units\":[";
    for(size_t i=0;i<geometry.points.size();++i) {
        if(i) out<<',';auto p=geometry.points[i];out<<'['<<double(p.x)*1000/em<<','<<double(p.y)*1000/em<<']';
    }
    out<<"]}";
}
static void write_observed_translation(std::ostream& out,const Geometry& single,const Geometry& repeated,
                                       double em) {
    if(single.points.empty() || repeated.points.size()!=2*single.points.size()) { out<<"null";return; }
    auto p=repeated.points.front(),q=repeated.points[single.points.size()];
    double dx=double(q.x)-p.x,dy=double(q.y)-p.y,residual=0;
    for(size_t i=0;i<single.points.size();++i) {
        auto a=repeated.points[i],b=repeated.points[i+single.points.size()];
        residual=std::max(residual,std::hypot((double(b.x)-a.x)-dx,(double(b.y)-a.y)-dy));
    }
    out<<"{\"vector_DIP\":["<<dx<<','<<dy<<"],\"vector_original_source_font_units\":["
       <<dx*1000/em<<','<<dy*1000/em<<"],\"maximum_nontranslation_residual_DIP\":"<<residual<<'}';
}
static void write_string_rows(std::ostream& out,const std::vector<std::string>& rows) {
    out<<'[';for(size_t i=0;i<rows.size();++i) { if(i) out<<',';out<<rows[i]; }out<<']';
}

int wmain(int argc,wchar_t** argv) {
    bool f2_witness=argc==5 && std::wcscmp(argv[4],L"--f2-witness")==0;
    if(argc!=4 && !f2_witness) { std::puts("{\"status\":\"FAILED\",\"error\":\"invalid_arguments\"}");return 2; }
    // This nominal-input witness survives the actual compiled avar. Its
    // observed outcome remains native data, never an assumed failure.
    const std::array<int,3> q_grid=f2_witness?std::array<int,3>{{1141,1453,10955}}:
                                               std::array<int,3>{{63,3072,0}},
                            nominal_grid=f2_witness?std::array<int,3>{{1141,7749,10955}}:
                                                     std::array<int,3>{{63,16384,0}};
    const std::array<double,3> q{{q_grid[0]/16384.,q_grid[1]/16384.,q_grid[2]/16384.}},
        user=f2_witness?std::array<double,3>{{534.820556640625,689.1845703125,834.320068359375}}:
                        std::array<double,3>{{501.922607421875,900,500}};
    std::vector<std::string> metric_rows,outline_rows;
    uint64_t axis_checks=0,metric_fields_checked=0,metric_failures=0,outline_pairs=0,
             point_pairs=0,point_failures=0,topology_failures=0;
    unsigned multiplier=0;UINT16 upm=0;double max_metric=0,max_outline=0;
    bool completed=false,unchanged=false;std::string left_sha,right_sha,error;
    try {
        TraceFont left(argv[1],true),right(argv[2],false);
        left_sha=left.digest;right_sha=right.digest;
        need(left.face.upm==right.face.upm,"trace_UPM_differs");upm=left.face.upm;multiplier=upm/1000;
        for(auto name:{"glyf","loca","hmtx","vmtx","cmap"}) {
            auto a=left.face.tables.find(tableTag(name)),b=right.face.tables.find(tableTag(name));
            need(a!=left.face.tables.end() && b!=right.face.tables.end() && a->second.second==b->second.second &&
                 std::memcmp(left.bytes.data()+a->second.first,right.bytes.data()+b->second.first,a->second.second)==0,
                 "trace_authored_default_table_differs");
        }
        for(unsigned a=0;a<3;++a) {
            auto axis=right.face.axes[a];
            need(user[a]>=axis.lo && user[a]<=axis.hi,"trace_nominal_user_outside_axis");
            double expected=axis.value+nominal_grid[a]/16384.*
                (nominal_grid[a]<0?axis.value-axis.lo:axis.hi-axis.value);
            need(expected==user[a],"trace_nominal_normalization_does_not_match_fixture");
        }
        ComPtr<IDWriteFactory6> factory;
        checked(DWriteCreateFactory(DWRITE_FACTORY_TYPE_ISOLATED,__uuidof(IDWriteFactory6),
                reinterpret_cast<IUnknown**>(factory.GetAddressOf())),"trace_native_factory_failed");
        ComPtr<IDWriteFontFile> lf,rf;
        checked(factory->CreateFontFileReference(argv[1],nullptr,&lf),"trace_reference_file_failed");
        checked(factory->CreateFontFileReference(argv[2],nullptr,&rf),"trace_target_file_failed");
        for(auto entry:{std::make_pair(lf.Get(),left.face_count),std::make_pair(rf.Get(),right.face_count)}) {
            BOOL supported=FALSE;DWRITE_FONT_FILE_TYPE type{};DWRITE_FONT_FACE_TYPE face_type{};UINT32 count=0;
            checked(entry.first->Analyze(&supported,&type,&face_type,&count),"trace_native_analyze_failed");
            need(supported && count==entry.second,"trace_native_support_or_face_count");
        }
        ComPtr<IDWriteFontResource> lr,rr;
        checked(factory->CreateFontResource(lf.Get(),0,&lr),"trace_reference_resource_failed");
        checked(factory->CreateFontResource(rf.Get(),0,&rr),"trace_target_resource_failed");
        auto reference=instance(lr.Get(),Q_TAGS,q,axis_checks),target=instance(rr.Get(),USER_TAGS,user,axis_checks);
        left.identity(reference.Get());right.identity(target.Get());
        constexpr UINT16 gid=2;
        for(BOOL sideways:{FALSE,TRUE}) {
            DWRITE_GLYPH_METRICS lm{},rm{};
            checked(reference->GetDesignGlyphMetrics(&gid,1,&lm,sideways),"trace_reference_metrics_failed");
            checked(target->GetDesignGlyphMetrics(&gid,1,&rm,sideways),"trace_target_metrics_failed");
            auto l=fields(lm),r=fields(rm);std::ostringstream metrics;metrics<<std::setprecision(17)
                <<"{\"sideways\":"<<(sideways?"true":"false")<<",\"fields\":[";
            for(unsigned j=0;j<7;++j) {
                double error_units=double(std::abs(l[j]-r[j]))/multiplier;
                ++metric_fields_checked;metric_failures+=error_units>LIMIT;max_metric=std::max(max_metric,error_units);
                if(j) metrics<<',';
                metrics<<"{\"name\":\""<<FIELD_NAMES[j]<<"\",\"reference_raw_design_integer\":"<<l[j]
                    <<",\"target_raw_design_integer\":"<<r[j]<<",\"reference_original_source_font_units\":"
                    <<double(l[j])/multiplier<<",\"target_original_source_font_units\":"<<double(r[j])/multiplier
                    <<",\"absolute_error_original_source_font_units\":"<<error_units<<'}';
            }
            metrics<<"]}";metric_rows.push_back(metrics.str());
            for(float em:{float(upm),1000.f,1000.5f,12.f,12.5f,16.25f}) {
                auto ls=trace_outline(reference.Get(),em,sideways,1,nullptr),
                     rs=trace_outline(target.Get(),em,sideways,1,nullptr);
                for(unsigned mode=0;mode<3;++mode) {
                    auto la=float(sideways?lm.advanceHeight:lm.advanceWidth)*em/upm,
                         ra=float(sideways?rm.advanceHeight:rm.advanceWidth)*em/upm;
                    std::array<float,2> lav{{la,la}},rav{{ra,ra}};
                    auto lg=mode==0?ls:trace_outline(reference.Get(),em,sideways,2,mode==2?lav.data():nullptr),
                         rg=mode==0?rs:trace_outline(target.Get(),em,sideways,2,mode==2?rav.data():nullptr);
                    bool topology=lg->structure==rg->structure && lg->points.size()==rg->points.size();
                    double maximum=0;uint64_t failures=0;
                    if(!topology) ++topology_failures;
                    else for(size_t i=0;i<lg->points.size();++i) {
                        auto a=lg->points[i],b=rg->points[i];
                        double difference=std::hypot(double(a.x)-b.x,double(a.y)-b.y)*1000/em;
                        maximum=std::max(maximum,difference);++point_pairs;failures+=difference>LIMIT;
                    }
                    max_outline=std::max(max_outline,maximum);point_failures+=failures;++outline_pairs;
                    std::ostringstream row;row<<std::setprecision(17)<<"{\"em_size_DIP\":"<<em
                        <<",\"sideways\":"<<(sideways?"true":"false")<<",\"run\":\""
                        <<(mode==0?"single_glyph":mode==1?"two_glyphs_implicit_advances":"two_glyphs_explicit_integer_design_advances")
                        <<"\",\"reference_advance_width_DIP_from_integer_design\":"<<double(lm.advanceWidth)*em/upm
                        <<",\"target_advance_width_DIP_from_integer_design\":"<<double(rm.advanceWidth)*em/upm
                        <<",\"reference_advance_height_DIP_from_integer_design\":"<<double(lm.advanceHeight)*em/upm
                        <<",\"target_advance_height_DIP_from_integer_design\":"<<double(rm.advanceHeight)*em/upm
                        <<",\"topology_equal\":"<<(topology?"true":"false")
                        <<",\"maximum_point_error_original_source_font_units\":"<<maximum
                        <<",\"point_failures_above_1_32\":"<<failures<<",\"reference\":";
                    write_points(row,*lg.Get(),em);row<<",\"target\":";write_points(row,*rg.Get(),em);
                    if(mode) {
                        row<<",\"reference_observed_repeat_translation\":";write_observed_translation(row,*ls.Get(),*lg.Get(),em);
                        row<<",\"target_observed_repeat_translation\":";write_observed_translation(row,*rs.Get(),*rg.Get(),em);
                        if(mode==2) row<<",\"reference_submitted_advance_DIP\":"<<la<<",\"target_submitted_advance_DIP\":"<<ra;
                    }
                    row<<'}';outline_rows.push_back(row.str());
                }
            }
        }
        left.unchanged();right.unchanged();unchanged=true;completed=true;
    } catch(const ProbeError& e) { error=e.what(); }
      catch(const std::exception&) { error="unexpected_trace_failure"; }
    bool strict=completed && !metric_failures && !point_failures && !topology_failures;
    std::ostringstream out;out<<std::setprecision(17)
        <<"{\"schema\":1,\"status\":\""<<(completed?"COMPLETED_AUTHORED_PRECISION_ROUNDING_TRACE_NOT_ACCEPTANCE":"FAILED")
        <<"\",\"data_origin\":\"self_authored_seven_GID_face_zero_only\",\"face_index\":0,\"GID\":2,"
        <<"\"case\":\""<<(f2_witness?"normalized_F2DOT14_composition_witness":"endpoint_rounding_witness")<<"\","
        <<"\"reference_q\":["<<q[0]<<','<<q[1]<<','<<q[2]<<"],\"reference_q_F2DOT14\":["
        <<q_grid[0]<<','<<q_grid[1]<<','<<q_grid[2]<<"],\"unchanged_target_nominal_user\":["
        <<user[0]<<','<<user[1]<<','<<user[2]<<"],\"nominal_normalized_before_avar_F2DOT14\":["
        <<nominal_grid[0]<<','<<nominal_grid[1]<<','<<nominal_grid[2]<<"],\"native_post_avar_coordinates\":\"NOT_OBSERVED\","
        <<"\"units_per_em\":"<<upm<<",\"precision_grid_multiplier\":"<<multiplier
        <<",\"reference_sha256\":\""<<left_sha<<"\",\"target_sha256\":\""<<right_sha<<"\","
        <<"\"source_files_unchanged\":"<<(unchanged?"true":"false")<<",\"native_protocol_completed\":"<<(completed?"true":"false")
        <<",\"within_1_32_native_parity\":"<<(strict?"true":"false")<<",\"strict_result\":\""<<(completed?(strict?"PASS":"FAIL"):"NOT_RUN")
        <<"\",\"limit_original_source_font_units\":"<<LIMIT<<",\"metric_fields_checked\":"<<metric_fields_checked
        <<",\"metric_fields_above_1_32\":"<<metric_failures<<",\"maximum_metric_error_original_source_font_units\":"<<max_metric
        <<",\"outline_pairs_checked\":"<<outline_pairs<<",\"outline_point_pairs_checked\":"<<point_pairs
        <<",\"outline_point_pairs_above_1_32\":"<<point_failures<<",\"outline_topology_failures\":"<<topology_failures
        <<",\"maximum_outline_error_original_source_font_units\":"<<max_outline<<",\"actual_FLOAT_and_readback_bits_checked\":"<<axis_checks
        <<",\"design_metrics_API\":\"resolution_independent_integer_design_fields_internal_rounding_not_inferred\","
        <<"\"outline_API\":\"floating_geometry_in_DIP_no_device_rasterization\","
        <<"\"implicit_repeat_translation\":\"observed_geometry_only_not_assumed_to_be_text_shaping_advance\","
        <<"\"GetGlyphPlacements\":\"NOT_RUN\",\"GDI_compatible_metrics\":\"NOT_RUN\","
        <<"\"rasterization\":\"NOT_RUN\",\"DPI_rendering\":\"NOT_RUN\",\"Windows11\":\"NOT_RUN\","
        <<"\"original_font\":\"NOT_RUN\",\"production_accepted\":false,\"design_metrics\":";
    write_string_rows(out,metric_rows);out<<",\"outline_observations\":";write_string_rows(out,outline_rows);
    out<<",\"error\":\""<<error<<"\"}\n";
    auto result=out.str();HANDLE file=CreateFileW(argv[3],GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(file==INVALID_HANDLE_VALUE) { std::puts("{\"status\":\"FAILED\",\"error\":\"trace_output_creation_failed\"}");return 2; }
    DWORD written=0;bool saved=result.size()<=MAXDWORD &&
        WriteFile(file,result.data(),DWORD(result.size()),&written,nullptr) && written==result.size();CloseHandle(file);
    if(!saved) { std::puts("{\"status\":\"FAILED\",\"error\":\"trace_output_write_failed\"}");return 2; }
    std::cout<<result;return completed?0:1;
}
#endif
