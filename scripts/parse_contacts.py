import re

def process_sql():
    with open(r'c:\Users\Pc\Downloads\CGR\Cotizador\isc_customer_contacts.sql', 'r', encoding='utf-8') as f:
        content = f.read()

    # Map original ISC codes to the Top 12 CLI-XXX IDs
    code_map = {
        "'RDIND'": "'CLI-001'",
        "'TORO'": "'CLI-002'",
        "'B&W'": "'CLI-004'",
        "'STONE MFG'": "'CLI-005'",
        "'ROM'": "'CLI-006'",
        "'SAFE FLEET'": "'CLI-006'",
        "'KNAPP'": "'CLI-007'",
        "'MILBA'": "'CLI-008'",
        "'JCI RUSKIN'": "'CLI-009'",
        "'GRIND'": "'CLI-010'",
        "'HUBBELL'": "'CLI-011'",
        "'NEOGEN'": "'CLI-012'"
    }

    for old_code, new_code in code_map.items():
        content = content.replace(old_code, new_code)

    new_sql = "-- Seed de contactos y direcciones traducido de isc_customer_contacts.sql\n\n"

    # 1. terminos_pago
    for match_pt in re.finditer(r'INSERT INTO payment_term \((.*?)\) VALUES\s*([\s\S]*?);\n', content):
        new_sql += "INSERT INTO terminos_pago (codigo, etiqueta, dias_netos, descuento_pct, dias_descuento, es_prepago, nota) VALUES\n"
        new_sql += match_pt.group(2) + ";\n\n"

    # 2. puestos_contacto
    for match_cp in re.finditer(r'INSERT INTO contact_position \((.*?)\) VALUES\s*([\s\S]*?);\n', content):
        new_sql += "INSERT INTO puestos_contacto (nombre, seq) VALUES\n"
        new_sql += match_cp.group(2) + ";\n\n"

    # 3. clientes (customer)
    # Exclude the mapped CLI-00X from being re-inserted to preserve their exact names and terms
    exclude_codes = [val.strip("'") for val in code_map.values()]
    
    for match_c in re.finditer(r'INSERT INTO customer \(code, name, terms, payment_term_code, tax_state, source\) VALUES\s*([\s\S]*?)\nON CONFLICT', content):
        values_text = match_c.group(1).strip()
        lines = values_text.split('\n')
        filtered_lines = []
        for line in lines:
            skip = False
            for code in exclude_codes:
                if f"('{code}'" in line:
                    skip = True
                    break
            if not skip:
                filtered_lines.append(line)
        
        if not filtered_lines:
            continue
            
        new_sql += "INSERT INTO clientes (cliente_id, razon_social, payment_terms, codigo_termino_pago, tax_state, origen_datos, es_estrella) VALUES\n"
        final_lines = []
        for line in filtered_lines:
            line = line.rstrip(',')
            if line.endswith(')'):
                line = line[:-1] + ", FALSE)"
            final_lines.append(line + ',')
        
        if final_lines:
            final_lines[-1] = final_lines[-1].rstrip(',')
            
        new_sql += '\n'.join(final_lines)
        new_sql += "\nON CONFLICT (cliente_id) DO UPDATE SET razon_social = EXCLUDED.razon_social, payment_terms = EXCLUDED.payment_terms, codigo_termino_pago = EXCLUDED.codigo_termino_pago, tax_state = EXCLUDED.tax_state, origen_datos = EXCLUDED.origen_datos;\n\n"

    # 4. cliente_direcciones (customer_address)
    for match_ca in re.finditer(r'INSERT INTO customer_address \((.*?)\) VALUES\s*([\s\S]*?);\n', content):
        new_sql += "INSERT INTO cliente_direcciones (id, cliente_id, direccion_bruta, calle, ciudad, codigo_estado, codigo_postal, es_principal) VALUES\n"
        new_sql += match_ca.group(2) + ";\n\n"

    # 5. cliente_contactos (customer_contact)
    for match_cc in re.finditer(r'INSERT INTO customer_contact \((.*?)\) VALUES\s*([\s\S]*?);\n', content):
        new_sql += "INSERT INTO cliente_contactos (id, cliente_id, direccion_id, nombre_completo, puesto, telefono, telefono_ext, telefono_bruto, es_cuenta_rol) VALUES\n"
        new_sql += match_cc.group(2) + ";\n\n"

    # 6. cliente_contacto_correos (customer_contact_email)
    for match_cce in re.finditer(r'INSERT INTO customer_contact_email \((.*?)\) VALUES\s*([\s\S]*?);\n', content):
        new_sql += "INSERT INTO cliente_contacto_correos (contacto_id, correo, es_principal, formato_valido) VALUES\n"
        new_sql += match_cce.group(2) + ";\n\n"

    with open(r'c:\Users\Pc\Downloads\CGR\Cotizador\sql\seed_contactos_isc.sql', 'w', encoding='utf-8') as f:
        f.write(new_sql)
    print("Created sql/seed_contactos_isc.sql successfully.")

if __name__ == '__main__':
    process_sql()
